"""Evaluate deterministic routing for supported deadline calculations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.temporal_evidence import should_use_deadline_calculation


def evaluate(cases: list[dict[str, object]]) -> dict[str, object]:
    records = []
    for case in cases:
        predicted = should_use_deadline_calculation(str(case["question"]))
        expected = bool(case["expected_route"])
        records.append(
            {
                **case,
                "predicted_route": predicted,
                "correct": predicted == expected,
            }
        )

    tp = sum(r["expected_route"] and r["predicted_route"] for r in records)
    fp = sum(not r["expected_route"] and r["predicted_route"] for r in records)
    fn = sum(r["expected_route"] and not r["predicted_route"] for r in records)
    tn = len(records) - tp - fp - fn
    return {
        "summary": {
            "cases": len(records),
            "correct": tp + tn,
            "accuracy": (tp + tn) / len(records),
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
            "external_api_calls": 0,
            "estimated_api_cost_usd": 0.0,
        },
        "failures": [record for record in records if not record["correct"]],
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "acceptance"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists():
        raise FileExistsError(f"output directory already exists: {args.output_dir}")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = evaluate(payload[args.split])
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "summary.json").write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "records.json").write_text(
        json.dumps(result["records"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"summary": result["summary"], "failures": result["failures"]},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
