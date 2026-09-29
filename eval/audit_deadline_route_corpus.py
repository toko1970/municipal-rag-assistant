"""Audit deadline-route changes across the fixed 500-question corpus."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from src.temporal_evidence import should_use_deadline_calculation


def legacy_route(question: str) -> bool:
    """Return the route decision used before the bounded route loop."""
    has_date = bool(
        re.search(r"\d{4}年\d{1,2}月\d{1,2}日", question)
        or re.search(r"\d{4}/\d{1,2}/\d{1,2}", question)
    )
    asks_deadline = any(
        phrase in question
        for phrase in ("期限", "締切", "いつまで", "具体的な日付", "何日まで")
    )
    return has_date and asks_deadline


def audit(rows: list[dict[str, str]]) -> dict[str, object]:
    records = []
    for row in rows:
        question = row["question"]
        before = legacy_route(question)
        after = should_use_deadline_calculation(question)
        records.append(
            {
                "question_id": row["question_id"],
                "scenario_id": row["scenario_id"],
                "variant_type": row["variant_type"],
                "question": question,
                "legacy_route": before,
                "current_route": after,
                "decision_changed": before != after,
            }
        )

    formal = [record for record in records if record["variant_type"] == "formal"]
    changed = [record for record in records if record["decision_changed"]]
    formal_changed = [record for record in formal if record["decision_changed"]]
    return {
        "summary": {
            "questions": len(records),
            "formal_questions": len(formal),
            "legacy_route_positive": sum(r["legacy_route"] for r in records),
            "current_route_positive": sum(r["current_route"] for r in records),
            "changed_questions": len(changed),
            "formal_legacy_route_positive": sum(r["legacy_route"] for r in formal),
            "formal_current_route_positive": sum(r["current_route"] for r in formal),
            "formal_changed_questions": len(formal_changed),
            "external_api_calls": 0,
            "estimated_api_cost_usd": 0.0,
        },
        "changed_records": changed,
        "current_route_records": [r for r in records if r["current_route"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        result = audit(list(csv.DictReader(handle)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "summary": result["summary"],
                "changed_records": result["changed_records"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
