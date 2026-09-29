"""Audit decomposition activation across the frozen 500-question corpus."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from config import BASE_DIR
from eval.rejected_query_trigger_candidate import decompose_query


DEFAULT_INPUT = BASE_DIR / "eval/evaluation_questions_500.csv"
EXPECTED_SCENARIOS = {"S032", "S059", "S088"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"監査出力は上書きしません: {args.output}")

    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    records = []
    for row in rows:
        applied = decompose_query(row["question"]) != [row["question"]]
        expected = row["scenario_id"] in EXPECTED_SCENARIOS
        if applied or expected:
            records.append(
                {
                    "question_id": row["question_id"],
                    "scenario_id": row["scenario_id"],
                    "variant_type": row["variant_type"],
                    "question": row["question"],
                    "expected_applied": expected,
                    "actual_applied": applied,
                    "ok": expected == applied,
                }
            )
    tp = sum(row["expected_applied"] and row["actual_applied"] for row in records)
    fp = sum(not row["expected_applied"] and row["actual_applied"] for row in records)
    fn = sum(row["expected_applied"] and not row["actual_applied"] for row in records)
    summary = {
        "corpus_count": len(rows),
        "expected_scenarios": sorted(EXPECTED_SCENARIOS),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": tp / (tp + fp) if tp + fp else 1.0,
        "recall": tp / (tp + fn) if tp + fn else 1.0,
        "failed_question_ids": [row["question_id"] for row in records if not row["ok"]],
        "records": records,
        "external_api_calls": 0,
        "sealed_holdout_accessed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
