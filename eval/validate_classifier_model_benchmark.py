"""Validate the fixed classifier-model benchmark and its factor gold contract."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


FACTOR_KEYS = (
    "retrieval_sufficient",
    "answer_fully_supported",
    "requires_case_facts",
    "requires_policy_judgment",
    "version_conflict",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def derive_label(factors: dict[str, bool]) -> str:
    if any(
        factors[key]
        for key in ("requires_case_facts", "requires_policy_judgment", "version_conflict")
    ):
        return "判断要"
    if not factors["retrieval_sufficient"] or not factors["answer_fully_supported"]:
        return "文書不足"
    return "根拠十分"


def validate_benchmark(dataset: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(dataset),
        key=lambda error: list(error.path),
    )
    if errors:
        messages = [
            f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        ]
        raise ValueError("Schema validationに失敗しました:\n" + "\n".join(messages))

    cases = dataset["cases"]
    if dataset["case_count"] != len(cases):
        raise ValueError("case_countとcases件数が一致しません")
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case_idが重複しています")

    expected_counts = Counter(case["expected_label"] for case in cases)
    if dict(expected_counts) != dataset["expected_counts"]:
        raise ValueError("expected_countsが実データと一致しません")
    modality_counts = Counter(case["modality"] for case in cases)
    if dict(modality_counts) != dataset["modality_counts"]:
        raise ValueError("modality_countsが実データと一致しません")
    factor_counts = {
        key: sum(case["expected_factors"][key] for case in cases)
        for key in FACTOR_KEYS
    }
    if factor_counts != dataset["factor_true_counts"]:
        raise ValueError("factor_true_countsが実データと一致しません")

    for case in cases:
        if derive_label(case["expected_factors"]) != case["expected_label"]:
            raise ValueError(f"factorから導出したラベルがgoldと一致しません: {case['case_id']}")
        evidence_ids = {item["element_id"] for item in case["evidence"]}
        for index, claim in enumerate(case["generated_answer"]["claims"], start=1):
            if claim["ordinal"] != index or claim["claim_id"] != f"claim-{index}":
                raise ValueError(f"claim順序が不正です: {case['case_id']}")
            unknown = set(claim["evidence_element_ids"]) - evidence_ids
            if unknown:
                raise ValueError(
                    f"claimが未取得evidenceを参照しています: {case['case_id']} / {sorted(unknown)}"
                )

    statuses = Counter(case["annotation_status"] for case in cases)
    if dataset["review_status"] == "approved" and statuses != {"approved": len(cases)}:
        raise ValueError("approved benchmarkには未承認annotationを残せません")
    if dataset["review_status"] == "draft" and statuses["approved"] == len(cases):
        raise ValueError("全annotationが承認済みならreview_statusもapprovedにします")

    if expected_counts["文書不足"] < 6:
        raise ValueError("文書不足caseは6件以上必要です")
    if modality_counts["visual"] < 6:
        raise ValueError("visual caseは6件以上必要です")
    for key in ("requires_case_facts", "requires_policy_judgment", "version_conflict"):
        if not 2 <= factor_counts[key] <= len(cases) - 2:
            raise ValueError(f"factorの正例・負例が不足しています: {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "design/schemas/classifier-model-benchmark-v1.schema.json",
    )
    args = parser.parse_args()
    dataset = load_json(args.dataset.resolve())
    schema = load_json(args.schema.resolve())
    validate_benchmark(dataset, schema)
    print(
        f"validated dataset={dataset['dataset_version']} cases={dataset['case_count']} "
        f"review_status={dataset['review_status']}"
    )


if __name__ == "__main__":
    main()
