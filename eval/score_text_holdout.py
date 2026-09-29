"""Open, review, and score frozen text holdout predictions after approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import BASE_DIR
from eval.validate_text_holdout_protocol import validate_public_manifest
from eval.validate_visual_fixture import load_json


DEFAULT_MANIFEST = BASE_DIR / "eval/text_holdout/public_manifest.json"
LABELS = {
    "grounded": "根拠十分",
    "needs_judgment": "判断要",
    "insufficient_documents": "文書不足",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR))
    except ValueError:
        return str(path.resolve())


def _wilson(successes: int, total: int, z: float = 1.96) -> dict[str, float]:
    if total == 0:
        return {"low": 0.0, "high": 0.0}
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return {
        "low": (centre - spread) / denominator,
        "high": (centre + spread) / denominator,
    }


def open_and_prepare_review(
    *,
    manifest_path: Path,
    sealed_root: Path,
    predictions_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"採点出力は上書きしません: {output_dir}")
    public_manifest = validate_public_manifest(manifest_path, BASE_DIR)
    if public_manifest["state"] != "PREDICTIONS_FROZEN":
        raise ValueError("gold開封にはPREDICTIONS_FROZEN stateが必要です")
    if _sha256(predictions_path) != public_manifest["predictions"]["sha256"]:
        raise ValueError("固定済みpredictionのhashが一致しません")
    manifest = validate_public_manifest(
        manifest_path, BASE_DIR, sealed_root=sealed_root
    )

    gold_path = sealed_root / "gold/scenario_gold.json"
    gold = load_json(gold_path)
    gold_by_id = {row["scenario_id"]: row for row in gold["scenarios"]}
    predictions = _read_jsonl(predictions_path)
    if len(predictions) != manifest["predictions"]["attempt_count"]:
        raise ValueError("prediction件数がmanifestと一致しません")

    review_rows = []
    for prediction in predictions:
        expected = gold_by_id[prediction["scenario_id"]]
        retrieved_documents = {
            row["document_id"] for row in prediction.get("retrieved", [])
        }
        expected_documents = set(expected["expected_document_ids"])
        expected_pairs = {
            (row["document_id"], row["heading"])
            for row in expected["expected_evidence"]
        }
        retrieved_pairs = {
            (row["document_id"], row["heading"])
            for row in prediction.get("retrieved", [])
        }
        document_retrieval_ok = (
            expected_documents <= retrieved_documents
            if expected["expected_corpus_answerability"]
            else True
        )
        evidence_retrieval_ok = (
            expected_pairs <= retrieved_pairs
            if expected["expected_corpus_answerability"]
            else True
        )
        review_rows.append(
            {
                "scenario_id": prediction["scenario_id"],
                "variant_type": prediction["variant_type"],
                "question": prediction["question"],
                "difficulty": expected["difficulty"],
                "expected_classification": expected["expected_classification"],
                "expected_label": LABELS[expected["expected_classification"]],
                "predicted_label": prediction.get("answer_label"),
                "classification_ok": prediction.get("answer_label")
                == LABELS[expected["expected_classification"]],
                "expected_answer_key": expected["expected_answer_key"],
                "answer": prediction.get("answer"),
                "content_ok": None,
                "content_review_note": "",
                "expected_document_ids": sorted(expected_documents),
                "retrieved_document_ids": sorted(retrieved_documents),
                "document_retrieval_ok": document_retrieval_ok,
                "evidence_retrieval_ok": evidence_retrieval_ok,
                "missing_conditions": expected["missing_conditions"],
                "execution_ok": prediction.get("status") == "SUCCESS",
                "error": prediction.get("error"),
            }
        )

    output_dir.mkdir(parents=True)
    review_path = output_dir / "content_review.jsonl"
    _write_jsonl(review_path, review_rows)
    opened_at = datetime.now(UTC).isoformat()
    opening = {
        "opened_at": opened_at,
        "scenario_hash_verified": True,
        "prediction_hash_verified": True,
        "review_path": _portable_path(review_path),
        "review_sha256": _sha256(review_path),
        "content_review_status": "PENDING",
    }
    _write_json(output_dir / "opening_summary.json", opening)
    manifest["state"] = "OPENED"
    manifest["opening"] = {
        "opened_at": opened_at,
        "scenario_hash_verified": True,
    }
    _write_json(manifest_path, manifest)
    return opening


def finalize_score(
    *, manifest_path: Path, review_path: Path, output_dir: Path
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    if manifest["state"] != "OPENED":
        raise ValueError("finalizeにはOPENED stateが必要です")
    rows = _read_jsonl(review_path)
    expected_count = manifest["questions"]["expression_count"]
    keys = {(row["scenario_id"], row["variant_type"]) for row in rows}
    if len(rows) != expected_count or len(keys) != expected_count:
        raise ValueError("reviewは100件の一意な表現である必要があります")
    if any(type(row.get("content_ok")) is not bool for row in rows):
        raise ValueError("全表現のcontent_okをbooleanで確定してください")

    for row in rows:
        row["composite_success"] = all(
            (
                row["execution_ok"],
                row["classification_ok"],
                row["document_retrieval_ok"],
                row["content_ok"],
            )
        )
    scenario_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        scenario_rows[row["scenario_id"]].append(row)
    scenario_stable = {
        scenario_id: all(row["composite_success"] for row in values)
        for scenario_id, values in scenario_rows.items()
    }
    successes = sum(row["composite_success"] for row in rows)
    stable = sum(scenario_stable.values())
    summary = {
        "holdout_id": manifest["holdout_id"],
        "expression_count": len(rows),
        "composite_success_count": successes,
        "composite_success_rate": successes / len(rows),
        "composite_wilson_95": _wilson(successes, len(rows)),
        "scenario_count": len(scenario_rows),
        "scenario_stability_count": stable,
        "scenario_stability_rate": stable / len(scenario_rows),
        "scenario_stability_wilson_95": _wilson(stable, len(scenario_rows)),
        "classification_success_count": sum(row["classification_ok"] for row in rows),
        "document_retrieval_success_count": sum(
            row["document_retrieval_ok"] for row in rows
        ),
        "evidence_retrieval_success_count": sum(
            row["evidence_retrieval_ok"] for row in rows
        ),
        "content_success_count": sum(row["content_ok"] for row in rows),
        "failure_counts": dict(
            Counter(
                reason
                for row in rows
                for reason, failed in (
                    ("execution", not row["execution_ok"]),
                    ("classification", not row["classification_ok"]),
                    ("document_retrieval", not row["document_retrieval_ok"]),
                    ("content", not row["content_ok"]),
                )
                if failed
            )
        ),
        "scored_at": datetime.now(UTC).isoformat(),
        "review_sha256": _sha256(review_path),
    }
    results_path = output_dir / "results.json"
    _write_json(results_path, summary)
    manifest["state"] = "CONSUMED"
    manifest["results"] = {
        "path": _portable_path(results_path),
        "sha256": _sha256(results_path),
    }
    _write_json(manifest_path, manifest)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    open_parser = subparsers.add_parser("open")
    open_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    open_parser.add_argument("--sealed-root", type=Path, required=True)
    open_parser.add_argument("--predictions", type=Path, required=True)
    open_parser.add_argument("--output-dir", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    finalize_parser.add_argument("--review", type=Path, required=True)
    finalize_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "open":
        result = open_and_prepare_review(
            manifest_path=args.manifest,
            sealed_root=args.sealed_root,
            predictions_path=args.predictions,
            output_dir=args.output_dir,
        )
    else:
        result = finalize_score(
            manifest_path=args.manifest,
            review_path=args.review,
            output_dir=args.output_dir,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
