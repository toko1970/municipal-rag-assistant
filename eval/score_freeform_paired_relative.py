"""Custodian-only aggregation for the blind relative holdout comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SYSTEMS = {"incumbent", "candidate"}
PAIR_STATUSES = {"RESOLVED", "UNRESOLVED", "OPERATIONAL_ERROR"}
ATTRIBUTIONS = {"LEFT", "RIGHT", "BOTH", "SHARED"}
EXPECTED_ACTION = {
    "grounded": "ANSWER",
    "needs_judgment": "HOLD",
    "insufficient_documents": "HOLD",
}


def _unique_index(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{label} has a missing {key}")
        if value in indexed:
            raise ValueError(f"duplicate {label} {key}: {value}")
        indexed[value] = row
    return indexed


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("bootstrap produced no replicates")
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _check_side_score(side: Any, pair_status: str, side_name: str) -> None:
    if not isinstance(side, dict):
        raise ValueError(f"{side_name} judgment must be an object")
    if pair_status == "OPERATIONAL_ERROR":
        return
    if side.get("g1") not in (0, 1, "UNRESOLVED") or isinstance(side.get("g1"), bool):
        raise ValueError(f"{side_name} G1 must be 0, 1, or UNRESOLVED")
    action = side.get("observed_decision")
    if action not in {"ANSWER", "HOLD", "UNRESOLVED"}:
        raise ValueError(f"{side_name} observed_decision is invalid")
    content = side.get("content_accuracy")
    if content not in {"PASS", "FAIL", "UNRESOLVED"}:
        raise ValueError(f"{side_name} content_accuracy is invalid")


def compute_custodian_gold_metrics(
    predictions: list[dict[str, Any]], gold: dict[str, Any]
) -> dict[str, Any]:
    """Compute only fixed-label and retrieval metrics that require no human judgment."""
    prediction_by_pair = _unique_index(predictions, "pair_id", "prediction pair")
    gold_by_scenario = _unique_index(gold.get("scenarios", []), "scenario_id", "gold scenario")
    class_counts = Counter(scenario["expected_classification"] for scenario in gold_by_scenario.values())
    retrieval_counts: Counter[str] = Counter()
    seen_expressions: set[tuple[str, str]] = set()
    for row in prediction_by_pair.values():
        scenario_id, variant_type = row.get("scenario_id"), row.get("variant_type")
        expression = (scenario_id, variant_type)
        if expression in seen_expressions:
            raise ValueError(f"duplicate retrieval expression: {scenario_id}/{variant_type}")
        seen_expressions.add(expression)
        expected = gold_by_scenario.get(scenario_id)
        if expected is None:
            raise ValueError(f"gold is missing scenario {scenario_id}")
        if not expected["expected_corpus_answerability"]:
            continue
        retrieval_counts["answerable_expressions"] += 1
        retrieved = {
            item.get("document_id")
            for item in row.get("retrieved_references", [])
        }
        expected_docs = set(expected["expected_document_ids"])
        if retrieved & expected_docs:
            retrieval_counts["any_required_document_hit"] += 1
        if expected_docs and expected_docs.issubset(retrieved):
            retrieval_counts["all_required_documents_hit"] += 1
    denominator = retrieval_counts["answerable_expressions"]
    return {
        "gold_classification_counts": {
            key: class_counts[key]
            for key in ("grounded", "needs_judgment", "insufficient_documents")
        },
        "retrieval_document_hit_at_8": {
            "any_required_document": {
                "numerator": retrieval_counts["any_required_document_hit"],
                "denominator": denominator,
            },
            "all_required_documents": {
                "numerator": retrieval_counts["all_required_documents_hit"],
                "denominator": denominator,
            },
        },
    }


def aggregate_paired_results(
    predictions: list[dict[str, Any]],
    review_map: list[dict[str, Any]],
    system_key: dict[str, Any],
    judgments: list[dict[str, Any]],
    gold: dict[str, Any],
    *,
    bootstrap_replicates: int = 10_000,
    seed: int = 20_261_024,
) -> dict[str, Any]:
    """Aggregate one paired run, excluding unresolved/error pairs symmetrically."""
    if bootstrap_replicates <= 0:
        raise ValueError("bootstrap_replicates must be positive")

    prediction_by_pair = _unique_index(predictions, "pair_id", "prediction pair")
    mapping_by_review = _unique_index(review_map, "review_id", "review mapping")
    mapping_by_pair = _unique_index(review_map, "pair_id", "review mapping pair")
    key_pairs = system_key.get("pairs")
    if not isinstance(key_pairs, list):
        raise ValueError("system key must contain pairs")
    key_by_pair = _unique_index(key_pairs, "pair_id", "system key pair")
    score_by_review = _unique_index(judgments, "review_id", "review")

    expected_pair_ids = set(prediction_by_pair)
    if set(mapping_by_pair) != expected_pair_ids or set(key_by_pair) != expected_pair_ids:
        raise ValueError("prediction, review-map, and system-key pairs do not match")
    if set(score_by_review) != set(mapping_by_review):
        raise ValueError("review rows do not match the review mapping")

    gold_by_scenario = _unique_index(gold.get("scenarios", []), "scenario_id", "gold scenario")
    assembled: list[dict[str, Any]] = []
    unresolved_attribution_by_side: Counter[str] = Counter()
    operational_errors: Counter[str] = Counter()
    operational_error_pairs = 0
    unresolved_pairs = 0
    for review_id, mapping in mapping_by_review.items():
        pair_id = mapping["pair_id"]
        pred = prediction_by_pair[pair_id]
        key = key_by_pair[pair_id]
        score = score_by_review[review_id]
        scenario_id = mapping["scenario_id"]
        if pred.get("scenario_id") != scenario_id or pred.get("variant_type") != mapping.get("variant_type"):
            raise ValueError(f"review map does not match frozen prediction pair {pair_id}")
        if scenario_id not in gold_by_scenario:
            raise ValueError(f"gold is missing scenario {scenario_id}")
        left_system, right_system = key.get("left_system"), key.get("right_system")
        if {left_system, right_system} != SYSTEMS:
            raise ValueError(f"invalid blinded system mapping for pair {pair_id}")
        statuses = {side: pred[side].get("status") for side in ("left", "right")}
        has_error = any(status != "SUCCESS" for status in statuses.values())
        expected_pair_status = "OPERATIONAL_ERROR" if has_error else None
        pair_status = score.get("pair_status")
        if pair_status not in PAIR_STATUSES:
            raise ValueError(f"invalid pair_status for review {review_id}")
        if expected_pair_status and pair_status != expected_pair_status:
            raise ValueError(f"operational-error pair must be marked separately: {review_id}")
        if not expected_pair_status and pair_status == "OPERATIONAL_ERROR":
            raise ValueError(f"successful response pair cannot be marked operational error: {review_id}")

        for blind_side, system in (("left", left_system), ("right", right_system)):
            if statuses[blind_side] != "SUCCESS":
                operational_errors[system] += 1
        if pair_status == "OPERATIONAL_ERROR":
            operational_error_pairs += 1
            assembled.append({"review_id": review_id, "pair_id": pair_id, "scenario_id": scenario_id,
                              "status": pair_status, "systems": {"left": left_system, "right": right_system},
                              "prediction": pred, "score": score, "gold": gold_by_scenario[scenario_id]})
            continue

        _check_side_score(score.get("left"), pair_status, "left")
        _check_side_score(score.get("right"), pair_status, "right")
        if pair_status == "RESOLVED":
            if score.get("unresolved_attribution") is not None:
                raise ValueError(f"resolved pair cannot have unresolved attribution: {review_id}")
            for side in ("left", "right"):
                if not isinstance(score[side].get("unsupported_assertion"), bool):
                    raise ValueError(f"resolved pair needs both unsupported_assertion judgments: {review_id}")
        else:
            unresolved_pairs += 1
            attribution = score.get("unresolved_attribution")
            if attribution not in ATTRIBUTIONS:
                raise ValueError(f"unresolved pair needs a valid attribution: {review_id}")
            if attribution in {"LEFT", "BOTH", "SHARED"}:
                unresolved_attribution_by_side[left_system] += 1
            if attribution in {"RIGHT", "BOTH", "SHARED"}:
                unresolved_attribution_by_side[right_system] += 1
        assembled.append({"review_id": review_id, "pair_id": pair_id, "scenario_id": scenario_id,
                          "status": pair_status, "systems": {"left": left_system, "right": right_system},
                          "prediction": pred, "score": score, "gold": gold_by_scenario[scenario_id]})

    # The only primary observations are resolved, operation-complete pairs.
    eligible = [row for row in assembled if row["status"] == "RESOLVED"]
    by_system: dict[str, list[tuple[str, bool]]] = {system: [] for system in SYSTEMS}
    paired_counts: Counter[str] = Counter()
    clusters: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for row in eligible:
        values: dict[str, bool] = {}
        for side, system in row["systems"].items():
            value = row["score"][side]["unsupported_assertion"]
            values[system] = value
            by_system[system].append((row["scenario_id"], value))
        incumbent_bad = values["incumbent"]
        candidate_bad = values["candidate"]
        if incumbent_bad and candidate_bad:
            paired_counts["both_unsupported"] += 1
        elif incumbent_bad:
            paired_counts["incumbent_only_unsupported"] += 1
        elif candidate_bad:
            paired_counts["candidate_only_unsupported"] += 1
        else:
            paired_counts["both_supported"] += 1
        clusters[row["scenario_id"]].append((incumbent_bad, candidate_bad))

    denominator = len(eligible)
    primary: dict[str, Any] = {
        "denominator": denominator,
        "incumbent": {"numerator": sum(value for _, value in by_system["incumbent"]),
                      "rate": (sum(value for _, value in by_system["incumbent"]) / denominator if denominator else None)},
        "candidate": {"numerator": sum(value for _, value in by_system["candidate"]),
                      "rate": (sum(value for _, value in by_system["candidate"]) / denominator if denominator else None)},
        "difference_incumbent_minus_candidate": None,
        "bootstrap_95_percentile": None,
        "bootstrap_replicates": bootstrap_replicates,
        "bootstrap_seed": seed,
        "eligible_scenario_clusters": len(clusters),
        "paired_outcomes": {key: paired_counts[key] for key in (
            "both_supported", "incumbent_only_unsupported", "candidate_only_unsupported", "both_unsupported")},
    }
    if denominator:
        point = primary["incumbent"]["rate"] - primary["candidate"]["rate"]
        primary["difference_incumbent_minus_candidate"] = point
        cluster_ids = sorted(clusters)
        if not cluster_ids:
            raise ValueError("no evaluable scenario clusters for bootstrap")
        rng = random.Random(seed)
        bootstrap_differences: list[float] = []
        for _ in range(bootstrap_replicates):
            sampled = [rng.choice(cluster_ids) for _ in cluster_ids]
            incumbent_n = candidate_n = sample_n = 0
            for cluster_id in sampled:
                for incumbent_bad, candidate_bad in clusters[cluster_id]:
                    incumbent_n += int(incumbent_bad)
                    candidate_n += int(candidate_bad)
                    sample_n += 1
            if not sample_n:
                raise ValueError("bootstrap replicate had no eligible paired expressions")
            bootstrap_differences.append((incumbent_n - candidate_n) / sample_n)
        interval = [_quantile(bootstrap_differences, 0.025), _quantile(bootstrap_differences, 0.975)]
        primary["bootstrap_95_percentile"] = interval
        primary["gate_status"] = "PASS" if point > 0 and interval[0] > 0 else "NO_CONFIRMED_IMPROVEMENT"
    else:
        primary["gate_status"] = "NO_ELIGIBLE_PAIRS"

    g1_rows = [row for row in assembled if row["status"] != "OPERATIONAL_ERROR"]
    g1_counts: Counter[str] = Counter()
    g1_unresolved = 0
    for row in g1_rows:
        left, right = row["score"]["left"].get("g1"), row["score"]["right"].get("g1")
        systems = row["systems"]
        vals = {systems["left"]: left, systems["right"]: right}
        if vals["incumbent"] == "UNRESOLVED" or vals["candidate"] == "UNRESOLVED":
            g1_unresolved += 1
        for system in SYSTEMS:
            if vals[system] == 1:
                g1_counts[system] += 1
        if vals["incumbent"] == 0 and vals["candidate"] == 1:
            g1_counts["candidate_only"] += 1
    if g1_counts["candidate_only"] or g1_counts["candidate"] > g1_counts["incumbent"]:
        g1_gate = "FAIL"
    elif g1_unresolved:
        g1_gate = "INCONCLUSIVE"
    else:
        g1_gate = "PASS"

    total_complete_pairs = sum(1 for row in assembled if row["status"] != "OPERATIONAL_ERROR")
    asymmetric_unresolved = unresolved_attribution_by_side["candidate"] != unresolved_attribution_by_side["incumbent"]
    unresolved_result = {
        "pair_count": unresolved_pairs,
        "excluded_responses_from_each_system": unresolved_pairs,
        "candidate_attributed_count": unresolved_attribution_by_side["candidate"],
        "incumbent_attributed_count": unresolved_attribution_by_side["incumbent"],
        "attribution_asymmetric": asymmetric_unresolved,
        "rate_denominator_per_system": total_complete_pairs,
    }

    # These fixed-label/retrieval metrics can be derived without reading judgments.
    auxiliary: dict[str, Any] = compute_custodian_gold_metrics(predictions, gold)
    action_counts: dict[str, Counter[str]] = {system: Counter() for system in SYSTEMS}
    content_counts: dict[str, Counter[str]] = {system: Counter() for system in SYSTEMS}
    for row in g1_rows:
        expected_action = EXPECTED_ACTION[row["gold"]["expected_classification"]]
        for side, system in row["systems"].items():
            side_score = row["score"][side]
            action = side_score.get("observed_decision")
            if action in {"ANSWER", "HOLD"}:
                action_counts[system]["denominator"] += 1
                action_counts[system]["correct"] += int(action == expected_action)
            if row["gold"]["expected_classification"] == "grounded":
                content = side_score.get("content_accuracy")
                if content in {"PASS", "FAIL"}:
                    content_counts[system]["denominator"] += 1
                    content_counts[system]["pass"] += int(content == "PASS")
    auxiliary["human_review_secondary"] = {
        "decision_accuracy": {
            system: {"numerator": action_counts[system]["correct"], "denominator": action_counts[system]["denominator"]}
            for system in sorted(SYSTEMS)
        },
        "grounded_content_accuracy": {
            system: {"numerator": content_counts[system]["pass"], "denominator": content_counts[system]["denominator"]}
            for system in sorted(SYSTEMS)
        },
    }

    overall_gate = "PASS"
    if primary["gate_status"] != "PASS" or g1_gate != "PASS" or asymmetric_unresolved:
        overall_gate = "INCONCLUSIVE" if primary["gate_status"] != "PASS" and g1_gate != "FAIL" else "FAIL"
        if asymmetric_unresolved and overall_gate != "FAIL":
            overall_gate = "INCONCLUSIVE"
    return {
        "primary": primary,
        "g1": {
            "incumbent_count": g1_counts["incumbent"],
            "candidate_count": g1_counts["candidate"],
            "candidate_only_count": g1_counts["candidate_only"],
            "unresolved_pair_count": g1_unresolved,
            "allowed_candidate_only_increase": 0,
            "gate_status": g1_gate,
        },
        "unresolved": unresolved_result,
        "operations": {
            "error_pair_count": operational_error_pairs,
            "errors_by_system": {system: operational_errors[system] for system in sorted(SYSTEMS)},
            "operation_complete_pair_count": total_complete_pairs,
        },
        "auxiliary": auxiliary,
        "adoption_status": overall_gate,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--review-map", type=Path, required=True)
    parser.add_argument("--system-key", type=Path, required=True)
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--holdout-manifest", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20_261_024)
    args = parser.parse_args()
    run_manifest = _read_json(args.run_manifest)
    holdout_manifest = _read_json(args.holdout_manifest)
    prediction_hash = hashlib.sha256(args.predictions.read_bytes()).hexdigest()
    gold_hash = hashlib.sha256(args.gold.read_bytes()).hexdigest()
    if prediction_hash != run_manifest.get("prediction_sha256"):
        raise ValueError("prediction file does not match frozen run manifest")
    if holdout_manifest.get("state") not in {"OPENED", "CONSUMED"}:
        raise ValueError("gold scoring requires an OPENED holdout")
    if gold_hash != (holdout_manifest.get("gold") or {}).get("scenario_sha256"):
        raise ValueError("gold file does not match frozen holdout manifest")
    if run_manifest.get("run_id") != (holdout_manifest.get("predictions") or {}).get("run_id"):
        raise ValueError("run ID does not match holdout manifest")
    if run_manifest.get("holdout", {}).get("holdout_id") != holdout_manifest.get("holdout_id"):
        raise ValueError("holdout ID does not match run manifest")
    manifest_root = Path(__file__).resolve().parents[1]
    questions_path = manifest_root / holdout_manifest["questions"]["path"]
    if not questions_path.is_file() or hashlib.sha256(questions_path.read_bytes()).hexdigest() != holdout_manifest["questions"]["sha256"]:
        raise ValueError("public questions do not match holdout manifest")
    if run_manifest["holdout"].get("questions_sha256") != holdout_manifest["questions"]["sha256"]:
        raise ValueError("questions hash does not match frozen paired run")
    if (holdout_manifest.get("predictions") or {}).get("sha256") != prediction_hash:
        raise ValueError("prediction hash does not match holdout manifest")
    system_key = _read_json(args.system_key)
    if system_key.get("run_id") != run_manifest.get("run_id"):
        raise ValueError("system key does not match frozen run")
    if len(_read_jsonl(args.predictions)) != 100:
        raise ValueError("paired holdout scoring requires 100 frozen expression pairs")
    result = aggregate_paired_results(
        _read_jsonl(args.predictions), _read_json(args.review_map), system_key,
        _read_jsonl(args.judgments), _read_json(args.gold),
        bootstrap_replicates=args.bootstrap_replicates, seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({"adoption_status": result["adoption_status"], "primary_denominator": result["primary"]["denominator"],
                      "unresolved_pairs": result["unresolved"]["pair_count"], "operational_error_pairs": result["operations"]["error_pair_count"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
