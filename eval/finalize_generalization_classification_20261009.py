"""Post-run semantic decisions and scenario aggregation; never calls a model."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "eval/results/generalization_completion_20261009/classification"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def event(row, prompt_version=None, event_type=None):
    return next((e for e in row.get("events", [])
                 if (prompt_version is None or e.get("prompt_version") == prompt_version)
                 and (event_type is None or e.get("type") == event_type)), None)


def paired(rows, excluded=frozenset()):
    by_scenario = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["scenario_id"] in excluded:
            continue
        by_scenario[row["scenario_id"]][row["arm"]].append(row["manual_final_composite"])
    categories = Counter()
    detail = {}
    for scenario, arms in sorted(by_scenario.items()):
        v1 = len(arms["v1"]) == 2 and all(arms["v1"])
        v2 = len(arms["v2"]) == 2 and all(arms["v2"])
        key = "both" if v1 and v2 else "v1_only" if v1 else "v2_only" if v2 else "neither"
        categories[key] += 1
        detail[scenario] = {"v1_both_expressions": v1, "v2_both_expressions": v2, "paired_category": key}
    return {"categories": dict(categories), "scenario_details": detail,
            "v1_success": categories["both"] + categories["v1_only"],
            "v2_success": categories["both"] + categories["v2_only"],
            "net_v2_minus_v1": categories["v2_only"] - categories["v1_only"]}


def main():
    source = read_jsonl(OUT / "service_records.jsonl")
    attempts = read_jsonl(OUT / "api_attempts.jsonl")
    assert len(source) == 88 and len(attempts) == 214
    gold = {r["id"]: r["gold"] for r in json.loads((OUT / "challenge.json").read_text())}
    initial = {r["index"]: r for r in read_jsonl(OUT / "semantic_review_oracle_initial.jsonl")}
    assert set(initial) == set(range(48))
    initial_key = {(r["row_id"], r["arm"]): r for r in initial.values()}
    retrieved_pass = {64, 67, 68, 69, 70, 72, 73, 74, 75, 78, 80, 81, 82, 84, 85, 86, 87}
    retrieved_extraction_fail = {69, 73, 81}
    retrieved_notes = {
        65: "算定額の質問に不要な個別支給照合を追加した過剰保留。",
        69: "最終正答だがQuestion Contractの文字化けはoracleと同じ。",
        71: "一般命題に不要なcase_factを追加しREVIEW_WITHOUT_CONDITIONで安全停止。",
        73: "最終正答だが質問外の条件付き金額facetは残存。",
        77: "cutoff_time schema違反で停止。date_calculationsも翌月3日と不整合。",
        78: "同一回答内の2028年2月＋翌月3日17時は一意に2028年3月3日17時を指す。独立レビューと一致。",
        79: "cutoff_time schema違反で停止。date_calculationsも翌月3日と不整合。",
        81: "個別照合を二つの余分なrequested facetへ分割したが最終回答は正答。",
        83: "真のcase_factを認識したがcondition_ids空でREVIEW_WITHOUT_CONDITION、安全停止。",
    }
    reviews = []
    for r in source:
        i = r["index"]
        if i < 48:
            review = dict(initial[i])
        elif i < 64:
            base = initial_key[(r["row_id"], r["arm"])]
            first = source[base["index"]]
            assert r["status"] == first["status"]
            assert (r.get("result") or {}).get("answer") == (first.get("result") or {}).get("answer")
            assert (r.get("result") or {}).get("question_contract") == (first.get("result") or {}).get("question_contract")
            review = {**base, "index": i, "repetition": 2,
                      "note": (base.get("note", "") + " 初回と最終表示・Question Contract完全一致。").strip()}
        else:
            review = {"index": i, "row_id": r["row_id"], "arm": r["arm"],
                      "evidence_mode": "retrieved", "repetition": 1,
                      "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
                      "rubric_version": "classification-rubric-v2.0",
                      "manual_final_composite": i in retrieved_pass,
                      "manual_question_extraction": (i not in retrieved_extraction_fail) if r["arm"] == "v2" else None,
                      "extraction_failure_reason": (
                          "oracleでも確認された質問外facet/文字化け" if i in retrieved_extraction_fail else None),
                      "note": retrieved_notes.get(i, ""),
                      "ambiguous_gold": r["row_id"] == "A01-paraphrase"}
        review["scenario_id"] = r["scenario_id"]
        review["status"] = r["status"]
        review["predicted_label"] = (r.get("result") or {}).get("answer_label")
        review["expected_label"] = gold[r["row_id"]]["label"]
        review["retrieved_doc_keys"] = r["retrieved_doc_keys"]
        if r["arm"] == "v2":
            cls = event(r, "classification-facet-v2-candidate")
            factors = (cls or {}).get("factors") or {}
            assessments = factors.get("facet_assessments", [])
            if assessments:
                expected_insufficient = gold[r["row_id"]]["label"] == "文書不足"
                review["coverage_axis_correct"] = ("insufficient" in [a["evidence_coverage"] for a in assessments]) == expected_insufficient
                types = {x["type"] for a in assessments for x in a["human_review_requirements"]}
                review["human_review_axis_correct"] = types == set(gold[r["row_id"]]["human_review_types"])
                review["human_review_types_predicted"] = sorted(types)
                # Index 23 is fully supported by B1 and question facts but marked partial;
                # index 35 omits the requested numeric amount while marked fully supported.
                review["claim_support_axis_correct"] = i not in {23, 35}
            else:
                review["coverage_axis_correct"] = None
                review["human_review_axis_correct"] = None
                review["claim_support_axis_correct"] = None
            gen = event(r, event_type="generation")
            answer_data = (gen or {}).get("response_data") or {}
            missing_types = [x["type"] for x in answer_data.get("missing_conditions", [])]
            review["generator_missing_condition_types"] = missing_types
            expected_types = set(gold[r["row_id"]]["human_review_types"])
            review["generator_condition_type_correct"] = set(missing_types) == expected_types if answer_data else None
        reviews.append(review)
    assert len(reviews) == 88
    (OUT / "semantic_review.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in reviews))
    oracle = [r for r in reviews if r["evidence_mode"] == "oracle" and r["repetition"] == 1]
    retrieved = [r for r in reviews if r["evidence_mode"] == "retrieved"]
    standard = paired(oracle)
    sensitivity = paired(oracle, {"A01", "B01"})
    alternative = [dict(r) for r in oracle]
    for r in alternative:
        if r["scenario_id"] == "B01" or (r["row_id"] == "A01-paraphrase" and r["arm"] == "v2"):
            r["manual_final_composite"] = False
    alternative_result = paired(alternative)
    cost_by_arm = Counter()
    for a in attempts:
        usage = a.get("usage") or {}
        inp = usage.get("prompt_token_count") or 0
        out = (usage.get("candidates_token_count") or 0) + (usage.get("thoughts_token_count") or 0)
        cost_by_arm[a["task"]["arm"]] += (inp * 0.3 + out * 2.5) / 1_000_000
    latency = {}
    for mode in ("oracle", "retrieved"):
        for arm in ("v1", "v2"):
            values = [r["latency_seconds"] for r in source if r["evidence_mode"] == mode and r["arm"] == arm]
            latency[f"{mode}_{arm}"] = {"n": len(values), "median_s": round(statistics.median(values), 3),
                                         "mean_s": round(statistics.mean(values), 3)}
    v2_oracle = [r for r in oracle if r["arm"] == "v2"]
    v2_retrieved = [r for r in retrieved if r["arm"] == "v2"]
    summary = {
        "status": "completed_challenge_not_adopted", "services": len(source), "api_attempts": len(attempts),
        "api_errors": sum(bool(a.get("error")) for a in attempts),
        "corrected_estimated_usd": sum(cost_by_arm.values()), "corrected_estimated_usd_by_arm": dict(cost_by_arm),
        "price_usd_per_million": {"input": 0.3, "output": 2.5}, "latency": latency,
        "oracle_primary": standard, "oracle_excluding_ambiguous_A01_B01": sensitivity,
        "oracle_alternative_individual_payment_reading": alternative_result,
        "oracle_expression_success": {arm: sum(r["manual_final_composite"] for r in oracle if r["arm"] == arm)
                                      for arm in ("v1", "v2")},
        "oracle_v2_stage": {
            "question_extraction": {"correct": sum(r["manual_question_extraction"] is True for r in v2_oracle), "total": 24},
            "coverage": {"correct": sum(r["coverage_axis_correct"] is True for r in v2_oracle),
                         "evaluable": sum(r["coverage_axis_correct"] is not None for r in v2_oracle)},
            "claim_support": {"correct": sum(r["claim_support_axis_correct"] is True for r in v2_oracle),
                              "evaluable": sum(r["claim_support_axis_correct"] is not None for r in v2_oracle)},
            "human_review": {"correct": sum(r["human_review_axis_correct"] is True for r in v2_oracle),
                             "evaluable": sum(r["human_review_axis_correct"] is not None for r in v2_oracle)},
            "generator_condition_type": {"correct": sum(r["generator_condition_type_correct"] is True for r in v2_oracle),
                                         "evaluable": sum(r["generator_condition_type_correct"] is not None for r in v2_oracle)},
            "final_display_composite": {"correct": sum(r["manual_final_composite"] for r in v2_oracle), "total": 24},
        },
        "retrieved_paired": paired(retrieved),
        "retrieved_expression_success": {arm: sum(r["manual_final_composite"] for r in retrieved if r["arm"] == arm)
                                         for arm in ("v1", "v2")},
        "retrieved_v2_stage": {
            "question_extraction": {"correct": sum(r["manual_question_extraction"] is True for r in v2_retrieved), "total": 12},
            "coverage": {"correct": sum(r["coverage_axis_correct"] is True for r in v2_retrieved),
                         "evaluable": sum(r["coverage_axis_correct"] is not None for r in v2_retrieved)},
            "claim_support": {"correct": sum(r["claim_support_axis_correct"] is True for r in v2_retrieved),
                              "evaluable": sum(r["claim_support_axis_correct"] is not None for r in v2_retrieved)},
            "human_review": {"correct": sum(r["human_review_axis_correct"] is True for r in v2_retrieved),
                             "evaluable": sum(r["human_review_axis_correct"] is not None for r in v2_retrieved)},
            "final_display_composite": {"correct": sum(r["manual_final_composite"] for r in v2_retrieved), "total": 12},
        },
        "repeat_exact_status_answer_contract": all(
            source[r["index"]]["status"] == source[initial_key[(r["row_id"], r["arm"])]["index"]]["status"]
            and (source[r["index"]].get("result") or {}).get("answer")
                == (source[initial_key[(r["row_id"], r["arm"])]["index"]].get("result") or {}).get("answer")
            and (source[r["index"]].get("result") or {}).get("question_contract")
                == (source[initial_key[(r["row_id"], r["arm"])]["index"]].get("result") or {}).get("question_contract")
            for r in reviews if r["repetition"] == 2),
        "stage_denominator_note": "B03 v2 generation schema failures precede classification; coverage/support/human axes are not evaluable for those two expressions.",
        "gate": "fail: net improvement below +2 and new v2-only composite regressions A03/B02. Do not proceed to 100/130/fresh holdout.",
    }
    write_json(OUT / "semantic_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
