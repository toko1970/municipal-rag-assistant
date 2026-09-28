"""Score the frozen visual holdout bundle after the gold opening checkpoint."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from config import BASE_DIR
from eval.evaluate_visual_extraction import evaluate_visual_extraction
from eval.validate_visual_fixture import load_json
from eval.validate_visual_holdout_protocol import validate_public_manifest
from src.visual_ingestion import load_visual_schema


PUBLIC_MANIFEST = BASE_DIR / "eval/visual_holdout/public_manifest.json"
DEFAULT_SEALED_ROOT = BASE_DIR / "eval/visual_holdout/.sealed"
LABELS = {
    "grounded": "根拠十分",
    "needs_judgment": "判断要",
    "insufficient_documents": "文書不足",
}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score_scenarios(
    predictions: list[dict[str, Any]], gold_scenarios: list[dict[str, Any]]
) -> dict[str, Any]:
    prediction_by_id = {item["scenario_id"]: item for item in predictions}
    gold_by_id = {item["scenario_id"]: item for item in gold_scenarios}
    if set(prediction_by_id) != set(gold_by_id):
        raise ValueError("predictionとscenario goldのIDが一致しません")
    completed = [
        item
        for item in predictions
        if item.get("status") != "BLOCKED_BY_EXTRACTION_ERROR"
    ]
    records = []
    for item in gold_scenarios:
        prediction = prediction_by_id[item["scenario_id"]]
        if prediction not in completed:
            continue
        classification_ok = (
            prediction.get("predicted_label") == LABELS[item["expected_classification"]]
        )
        required_documents = item.get("required_document_ids", [])
        retrieved_documents = prediction.get("retrieved_document_ids", [])
        required_document_retrieved = all(
            document_id in retrieved_documents for document_id in required_documents
        )
        answer = str(prediction.get("answer", "")).casefold()
        answer_key_terms = item.get("expected_answer_key_terms", [])
        answer_key_covered = all(
            str(term).casefold() in answer for term in answer_key_terms
        )
        records.append(
            {
                "scenario_id": item["scenario_id"],
                "classification_ok": classification_ok,
                "required_document_retrieved": required_document_retrieved,
                "answer_key_covered": answer_key_covered,
                "end_to_end_success": (
                    classification_ok
                    and required_document_retrieved
                    and answer_key_covered
                ),
            }
        )
    classification_correct = sum(record["classification_ok"] for record in records)
    retrieval_correct = sum(record["required_document_retrieved"] for record in records)
    answer_key_correct = sum(record["answer_key_covered"] for record in records)
    end_to_end_success = sum(record["end_to_end_success"] for record in records)
    expected_counts = {
        label: sum(item["expected_classification"] == label for item in gold_scenarios)
        for label in LABELS
    }
    return {
        "scenario_count": len(gold_scenarios),
        "completed_answer_count": len(completed),
        "blocked_by_extraction_error_count": len(predictions) - len(completed),
        "classification_evaluated_count": len(completed),
        "classification_correct_count": classification_correct,
        "classification_accuracy": (
            classification_correct / len(completed) if completed else None
        ),
        "answer_content_evaluated_count": len(completed),
        "required_document_retrieved_count": retrieval_correct,
        "required_document_retrieval_rate": (
            retrieval_correct / len(completed) if completed else None
        ),
        "answer_key_covered_count": answer_key_correct,
        "answer_key_coverage_rate": (
            answer_key_correct / len(completed) if completed else None
        ),
        "end_to_end_success_count": end_to_end_success,
        "end_to_end_success_rate": end_to_end_success / len(gold_scenarios),
        "expected_classification_counts": expected_counts,
        "records": records,
    }


def acceptance_verdict(
    *,
    extraction: dict[str, Any],
    scenarios: dict[str, Any],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    document_count = extraction["sealed_document_count"]
    scenario_count = scenarios["scenario_count"]
    measured = {
        "schema_valid_document_rate": (
            extraction["schema_valid_count"] / document_count if document_count else 0.0
        ),
        "completed_answer_rate": (
            scenarios["completed_answer_count"] / scenario_count
            if scenario_count
            else 0.0
        ),
        "classification_accuracy": scenarios["classification_accuracy"] or 0.0,
        "required_document_retrieval_rate": (
            scenarios["required_document_retrieval_rate"] or 0.0
        ),
        "answer_key_coverage_rate": scenarios["answer_key_coverage_rate"] or 0.0,
        "end_to_end_success_rate": scenarios["end_to_end_success_rate"],
    }
    checks = {
        name: {
            "actual": measured[name],
            "threshold": threshold,
            "passed": measured[name] >= threshold,
        }
        for name, threshold in thresholds.items()
    }
    return {"passed": all(item["passed"] for item in checks.values()), "checks": checks}


def score_extractions(
    extraction_records: list[dict[str, Any]],
    extraction_gold: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    gold_by_id = {
        item["document_id"]: item["annotation"] for item in extraction_gold["documents"]
    }
    schema = load_visual_schema()
    results = []
    for record in extraction_records:
        result = {
            "document_id": record["document_id"],
            "schema_status": record["status"],
            "schema_error": record.get("error"),
            "metrics": None,
        }
        if record["status"] == "VALID":
            candidate = load_json(repository_root / record["normalized_path"])
            result["metrics"] = asdict(
                evaluate_visual_extraction(
                    candidate,
                    gold_by_id[record["document_id"]],
                    schema,
                )
            )
        results.append(result)
    measured = [item for item in results if item["metrics"] is not None]
    return {
        "sealed_document_count": len(gold_by_id),
        "extraction_attempt_count": len(extraction_records),
        "schema_valid_count": len(measured),
        "schema_invalid_count": len(extraction_records) - len(measured),
        "unattempted_document_count": len(gold_by_id) - len(extraction_records),
        "gate_evaluated_count": len(measured),
        "gate_passed_count": sum(
            bool(item["metrics"]["gate_passed"]) for item in measured
        ),
        "records": results,
    }


def score_opened_holdout(
    *, manifest_path: Path, sealed_root: Path, output_path: Path
) -> tuple[dict[str, Any], str]:
    manifest = validate_public_manifest(manifest_path, BASE_DIR, sealed_root)
    if manifest["state"] != "OPENED":
        raise ValueError("採点開始時のstateはOPENEDである必要があります")
    predictions_path = (
        BASE_DIR
        / "eval/results"
        / manifest["predictions"]["run_id"]
        / "predictions.json"
    )
    bundle = load_json(predictions_path)
    extraction_gold = load_json(sealed_root / "gold/extraction_gold.json")
    scenario_gold = load_json(sealed_root / "gold/scenario_gold.json")
    blueprint = load_json(BASE_DIR / manifest["blueprint"]["path"])
    extraction = score_extractions(bundle["extractions"], extraction_gold, BASE_DIR)
    scenarios = score_scenarios(bundle["predictions"], scenario_gold["scenarios"])
    extraction_failed = extraction["schema_invalid_count"] > 0
    result = {
        "schema_version": "1.0",
        "holdout_id": manifest["holdout_id"],
        "run_id": manifest["predictions"]["run_id"],
        "candidate_git_commit": manifest["candidate"]["git_commit"],
        "prediction_sha256": manifest["predictions"]["sha256"],
        "gold_hash_verified": {
            "extraction": manifest["opening"]["extraction_hash_verified"],
            "scenario": manifest["opening"]["scenario_hash_verified"],
        },
        "pipeline_stage_status": {
            "visual_extraction": "FAILED" if extraction_failed else "COMPLETED",
            "retrieval": "NOT_EXECUTED" if extraction_failed else "COMPLETED",
            "answer_generation": "NOT_EXECUTED" if extraction_failed else "COMPLETED",
            "answer_classification": "NOT_EXECUTED"
            if extraction_failed
            else "COMPLETED",
        },
        "extraction": extraction,
        "scenarios": scenarios,
        "acceptance": acceptance_verdict(
            extraction=extraction,
            scenarios=scenarios,
            thresholds=blueprint["acceptance_thresholds"],
        ),
        "failure_attribution": (
            {
                "primary_category": "visual_extraction_schema_failure",
                "failed_document_id": bundle["summary"]["failed_document_id"],
                "detail": bundle["summary"]["failure"],
                "cascading_blocked_scenarios": len(bundle["predictions"]),
            }
            if extraction_failed
            else None
        ),
        "holdout_reusable_as_unseen": False,
    }
    if output_path.exists():
        raise FileExistsError(f"scoreは上書きしません: {output_path}")
    _write_json(output_path, result)
    return result, _sha256(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PUBLIC_MANIFEST)
    parser.add_argument("--sealed-root", type=Path, default=DEFAULT_SEALED_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result, result_hash = score_opened_holdout(
        manifest_path=args.manifest.resolve(),
        sealed_root=args.sealed_root.resolve(),
        output_path=args.output.resolve(),
    )
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "sha256": result_hash,
                "primary_failure": (
                    result["failure_attribution"]["primary_category"]
                    if result["failure_attribution"]
                    else None
                ),
                "acceptance_passed": result["acceptance"]["passed"],
                "end_to_end_success_count": result["scenarios"][
                    "end_to_end_success_count"
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
