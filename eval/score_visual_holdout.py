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
    classification_correct = sum(
        prediction_by_id[item["scenario_id"]].get("predicted_label")
        == LABELS[item["expected_classification"]]
        for item in gold_scenarios
        if prediction_by_id[item["scenario_id"]] in completed
    )
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
        "end_to_end_success_count": 0,
        "end_to_end_success_rate": 0.0,
        "expected_classification_counts": expected_counts,
    }


def score_extractions(
    extraction_records: list[dict[str, Any]],
    extraction_gold: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    gold_by_id = {
        item["document_id"]: item["annotation"]
        for item in extraction_gold["documents"]
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
            "visual_extraction": "FAILED",
            "retrieval": "NOT_EXECUTED",
            "answer_generation": "NOT_EXECUTED",
            "answer_classification": "NOT_EXECUTED",
        },
        "extraction": score_extractions(
            bundle["extractions"], extraction_gold, BASE_DIR
        ),
        "scenarios": score_scenarios(
            bundle["predictions"], scenario_gold["scenarios"]
        ),
        "failure_attribution": {
            "primary_category": "visual_extraction_schema_failure",
            "failed_document_id": bundle["summary"]["failed_document_id"],
            "detail": bundle["summary"]["failure"],
            "cascading_blocked_scenarios": len(bundle["predictions"]),
        },
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
                "primary_failure": result["failure_attribution"]["primary_category"],
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
