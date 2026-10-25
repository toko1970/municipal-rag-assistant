"""Summarize frozen paired classification services without additional API use."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval/results/generalization_completion_20261009/classification"


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def compact(text):
    return re.sub(r"[\s,，、]", "", text or "")


def stage(row, gold):
    result = row.get("result") or {}
    events = row.get("events") or []
    stages = {"question_extraction": None, "evidence_coverage": None,
              "claim_support": None, "human_review": None, "final_display": None}
    contract = result.get("question_contract")
    if contract is None:
        contract_events = [e for e in events if e.get("type") == "classification"
                           and e.get("prompt_version") == "question-contract-v1"]
        if contract_events:
            contract = (contract_events[-1].get("factors") or {}).get("question_contract")
    if contract is not None:
        requirements = [f.get("requirement", "") for f in contract.get("requested_facets", [])]
        stages["question_extraction"] = {
            "status": contract.get("status"), "requirements": requirements,
            "expected": gold["requested_facets"],
            "automatic_count_match": len(requirements) == len(gold["requested_facets"]),
            "manual_semantic_review_required": True,
        }
        classification_events = [e for e in events if e.get("type") == "classification"
                                 and e.get("prompt_version") == "classification-facet-v2-candidate"]
        if classification_events:
            factors = classification_events[-1].get("factors") or {}
            assessments = factors.get("facet_assessments", [])
            predicted_coverage = [f.get("evidence_coverage") for f in assessments]
            expected_insufficient = gold["label"] == "文書不足"
            stages["evidence_coverage"] = {
                "predicted": predicted_coverage,
                "automatic_match": ("insufficient" in predicted_coverage) == expected_insufficient,
                "manual_semantic_review_required": len(assessments) != len(requirements),
            }
            stages["claim_support"] = {
                "predicted": [f.get("claim_support") for f in assessments],
                "manual_semantic_review_required": True,
            }
            reviews = [v.get("type") for f in assessments for v in f.get("human_review_requirements", [])]
            stages["human_review"] = {
                "predicted": reviews, "expected": gold["human_review_types"],
                "automatic_match": set(reviews) == set(gold["human_review_types"]),
            }
    text = result.get("answer", "")
    required = gold.get("required_answer_terms", [])
    forbidden = gold.get("forbidden_answer_terms", [])
    missing = [term for term in required if compact(term) not in compact(text)]
    present_forbidden = [term for term in forbidden if compact(term) in compact(text)]
    status = result.get("answer_status", row.get("status"))
    label = result.get("answer_label")
    stages["final_display"] = {
        "status": status, "label": label, "expected_label": gold["label"],
        "label_match": status == "SUCCESS" and label == gold["label"],
        "missing_required_terms": missing, "present_forbidden_terms": present_forbidden,
        "automatic_composite": status == "SUCCESS" and label == gold["label"] and not missing and not present_forbidden,
        "manual_semantic_review_required": True,
    }
    return stages


def main():
    challenge = {row["id"]: row for row in json.loads((OUT / "challenge.json").read_text())}
    records = load_jsonl(OUT / "service_records.jsonl")
    attempts = load_jsonl(OUT / "api_attempts.jsonl")
    scored = []
    for row in records:
        gold = challenge[row["row_id"]]["gold"]
        scored.append({"index": row["index"], "row_id": row["row_id"],
                       "scenario_id": row["scenario_id"], "arm": row["arm"],
                       "mode": row["evidence_mode"], "repetition": row["repetition"],
                       "gold": gold, "stages": stage(row, gold)})
    (OUT / "automatic_checks.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in scored))
    counts = Counter((r["mode"], r["arm"], r["stages"]["final_display"]["automatic_composite"])
                     for r in scored)
    by_key = {(r["row_id"], r["mode"], r["repetition"], r["arm"]): r for r in scored}
    paired = Counter()
    for row in challenge.values():
        key = (row["id"], "oracle", 1)
        v1 = by_key.get((*key, "v1"))
        v2 = by_key.get((*key, "v2"))
        if v1 and v2:
            a = v1["stages"]["final_display"]["automatic_composite"]
            b = v2["stages"]["final_display"]["automatic_composite"]
            paired["both" if a and b else "v1_only" if a else "v2_only" if b else "neither"] += 1
    corrected_price = {"input_usd_per_million": 0.30, "output_usd_per_million": 2.50}
    corrected_cost = 0.0
    for attempt in attempts:
        usage = attempt.get("usage") or {}
        inp = usage.get("prompt_token_count") or 0
        out = (usage.get("candidates_token_count") or 0) + (usage.get("thoughts_token_count") or 0)
        corrected_cost += (inp * corrected_price["input_usd_per_million"]
                           + out * corrected_price["output_usd_per_million"]) / 1_000_000
    report = {"service_records": len(records), "api_attempts": len(attempts),
              "api_errors": [dict(task=r.get("task"), phase=r.get("phase"), error=r.get("error"))
                             for r in attempts if r.get("error")],
              "estimated_usd": sum(r.get("estimated_usd", 0) for r in attempts),
              "corrected_estimated_usd": corrected_cost,
              "corrected_price_assumption": corrected_price,
              "corrected_price_source": "2026-10-09 official pricing URL recorded in eval/results/generalization_validation_20261009_gemini35/manifest.json",
              "automatic_counts": {str(k): v for k, v in sorted(counts.items())},
              "oracle_expression_pairs": dict(paired),
              "caution": "Automatic terms and facet counts are provisional. Manual review of each claim, semantic facet coverage, and unsafe assertions required before gate."}
    (OUT / "automatic_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
