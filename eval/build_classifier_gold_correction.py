"""Re-score saved regression labels after reviewed gold-scope corrections."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "eval/results/version_resolver_regression_v1/analysis.json"
MANIFEST = ROOT / "eval/evaluation_set_manifest.json"
OUTPUT = ROOT / "eval/results/classifier_gold_correction_v2/analysis.json"

CORRECTIONS = {
    "Q006": ("S002", "文書不足", "根拠十分"),
    "Q046": ("S010", "判断要", "根拠十分"),
    "Q076": ("S016", "文書不足", "根拠十分"),
    "Q086": ("S018", "判断要", "根拠十分"),
    "Q176": ("S036", "判断要", "根拠十分"),
    "Q301": ("S061", "判断要", "根拠十分"),
    "Q316": ("S064", "判断要", "根拠十分"),
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, Any]:
    source = read_json(SOURCE)
    manifest = read_json(MANIFEST)
    rows = []
    for row in source["ledger"]:
        item_id = row["id"]
        expected = CORRECTIONS.get(
            item_id, (None, row["expected_label"], row["expected_label"])
        )[2]
        predicted = row["resolver_candidate_label"]
        old_cause = row["resolver_candidate_cause"]
        new_correct = predicted == expected
        new_cause = old_cause
        if old_cause == "classification_failure" and new_correct:
            new_cause = "success"
        elif old_cause == "success" and not new_correct:
            new_cause = "classification_failure"
        rows.append(
            {
                "id": item_id,
                "expected_label": expected,
                "predicted_label": predicted,
                "classification_ok": new_correct,
                "primary_cause": new_cause,
            }
        )

    counts = Counter(row["primary_cause"] for row in rows)
    classification_mismatches = sorted(
        row["id"] for row in rows if not row["classification_ok"]
    )
    primary_classification_failures = sorted(
        row["id"] for row in rows if row["primary_cause"] == "classification_failure"
    )
    corrections = [
        {
            "question_id": question_id,
            "scenario_id": scenario_id,
            "old_label": old_label,
            "new_label": new_label,
        }
        for question_id, (scenario_id, old_label, new_label) in CORRECTIONS.items()
    ]
    return {
        "artifact_version": "classifier-gold-correction-v2",
        "correction_type": "gold_scope_correction",
        "evaluation_set_version": manifest["version"],
        "corrections": corrections,
        "summary": {
            "total": len(rows),
            "success": counts["success"],
            "classification_correct": sum(row["classification_ok"] for row in rows),
            "primary_causes": dict(sorted(counts.items())),
            "classification_mismatches": classification_mismatches,
            "primary_classification_failures": primary_classification_failures,
        },
        "model_or_prompt_changed": False,
        "external_api_calls": 0,
        "sealed_holdout_accessed": False,
        "source_sha256": {
            str(SOURCE.relative_to(ROOT)): sha256(SOURCE),
            str(MANIFEST.relative_to(ROOT)): sha256(MANIFEST),
        },
    }


def main() -> None:
    result = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
