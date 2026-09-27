"""Classify retrieval failures into document and section selection failures."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


FAILURE_FIELDS = [
    "question_id",
    "question",
    "failure_category",
    "difficulty",
    "expected_answer_type",
    "expected_document_ids",
    "expected_evidence",
    "retrieved_document_ids",
    "retrieved_headings",
    "required_document_count",
    "required_evidence_count",
]


def _is_true(value: object) -> bool:
    return str(value).strip() in {"1", "1.0", "true", "True"}


def _pipe_count(value: object) -> int:
    return len([item for item in str(value or "").split("|") if item.strip()])


def load_results(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def classify_record(record: dict[str, object], k: int) -> str:
    """Classify an evidence-scored row at k.

    ``document_missing`` includes partial retrieval for multi-document questions.
    ``section_missing`` means every required document is present but at least one
    required evidence heading is absent.
    """
    if not _is_true(record.get("retrieval_applicable")):
        return "not_applicable"
    if not record.get("expected_evidence"):
        return "not_evidence_scored"
    if _is_true(record.get(f"evidence_hit_at_{k}")):
        return "success"
    if not _is_true(record.get(f"hit_at_{k}")):
        return "document_missing"
    return "section_missing"


def _counter_dict(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def analyze_records(
    records: list[dict[str, object]], k: int
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if k not in {1, 3, 5}:
        raise ValueError("kは1、3、5のいずれかにしてください")

    categories = [(record, classify_record(record, k)) for record in records]
    scored = [item for item in categories if item[1] not in {"not_applicable", "not_evidence_scored"}]
    failures = [item for item in scored if item[1] != "success"]
    failure_rows = []
    for record, category in failures:
        failure_rows.append(
            {
                **{field: record.get(field, "") for field in FAILURE_FIELDS[:-2]},
                "failure_category": category,
                "required_document_count": _pipe_count(
                    record.get("expected_document_ids")
                ),
                "required_evidence_count": _pipe_count(
                    record.get("expected_evidence")
                ),
            }
        )

    category_counts = Counter(category for _record, category in scored)
    summary = {
        "k": k,
        "total_rows": len(records),
        "retrieval_not_applicable": sum(
            category == "not_applicable" for _record, category in categories
        ),
        "evidence_scored": len(scored),
        "success": category_counts["success"],
        "failure": len(failures),
        "failure_categories": {
            "document_missing": category_counts["document_missing"],
            "section_missing": category_counts["section_missing"],
        },
        "failure_by_difficulty": _counter_dict(
            record.get("difficulty", "") for record, _category in failures
        ),
        "failure_by_answer_type": _counter_dict(
            record.get("expected_answer_type", "") for record, _category in failures
        ),
        "failure_by_required_document_count": _counter_dict(
            str(_pipe_count(record.get("expected_document_ids")))
            for record, _category in failures
        ),
        "failure_by_required_evidence_count": _counter_dict(
            str(_pipe_count(record.get("expected_evidence")))
            for record, _category in failures
        ),
    }
    return summary, failure_rows


def save_failures(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FAILURE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--failures-output", type=Path, required=True)
    args = parser.parse_args()

    records = load_results(args.input)
    summaries = {}
    failures_at_5 = []
    for k in (1, 3, 5):
        summary, failures = analyze_records(records, k)
        summaries[f"at_{k}"] = summary
        if k == 5:
            failures_at_5 = failures

    payload = {"input": str(args.input), "analysis": summaries}
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    save_failures(failures_at_5, args.failures_output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
