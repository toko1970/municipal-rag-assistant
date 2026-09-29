"""Apply saved Version Resolver outputs to the fixed 130-question regression."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.answering import (
    ClassificationFactors,
    ClassificationResult,
    derive_label,
    parse_answer_output,
    render_display_answer,
)
from src.version_resolution import parse_version_resolution


CONFIDENCE_THRESHOLD = 0.80


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def _read_jsonl(path: Path, id_field: str) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    result = {row[id_field]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"IDが重複しています: {path}")
    return result


def _answer_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "claims": [
            {
                "claim_id": claim["claim_id"],
                "ordinal": claim["ordinal"],
                "text": claim["text"],
                "evidence_element_ids": claim["evidence_element_ids"],
                "evidence_kind": claim.get("evidence_kind", "text"),
            }
            for claim in record["claims"]
        ],
        "missing_conditions": record["missing_conditions"],
    }


def _production_cause(row: dict[str, Any]) -> str:
    if (
        row["primary_cause"] == "classification_failure"
        and row["previous_decision_classification_ok"]
    ):
        return "success"
    return row["primary_cause"]


def analyze(
    baseline: dict[str, Any],
    text_records: dict[str, dict[str, Any]],
    resolver_records: dict[str, dict[str, Any]],
    *,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    ledger = []
    seen_resolver_ids: set[str] = set()
    for baseline_row in baseline["ledger"]:
        row = dict(baseline_row)
        item_id = row["id"]
        baseline_cause = _production_cause(row)
        candidate_label = row["previous_decision_label"]
        candidate_ok = row["previous_decision_classification_ok"]
        resolver_status = "NOT_REQUIRED"
        resolver_applied = False
        version_factor_changed = False

        if item_id in resolver_records:
            if row["modality"] != "text" or item_id not in text_records:
                raise ValueError(f"resolver対象のtext recordがありません: {item_id}")
            seen_resolver_ids.add(item_id)
            text = text_records[item_id]
            factors = ClassificationFactors(**text["classification_factors"])
            if not factors.version_conflict:
                raise ValueError(f"baselineでversion conflictではありません: {item_id}")
            resolver = resolver_records[item_id]
            if resolver["error"] is not None:
                resolver_status = "RESOLUTION_FAILED"
            else:
                resolution = parse_version_resolution(resolver["response"])
                if resolution.confidence < confidence_threshold:
                    resolver_status = "LOW_CONFIDENCE_FALLBACK"
                else:
                    candidate = ClassificationResult(
                        factors=replace(
                            factors, version_conflict=resolution.version_conflict
                        ),
                        confidence=1.0,
                    )
                    try:
                        render_display_answer(
                            parse_answer_output(_answer_payload(text)), candidate
                        )
                    except ValueError:
                        resolver_status = "DISPLAY_CONTRACT_FALLBACK"
                    else:
                        resolver_status = "SUCCESS"
                        resolver_applied = True
                        version_factor_changed = (
                            resolution.version_conflict != factors.version_conflict
                        )
                        candidate_label = derive_label(candidate.factors)
                        candidate_ok = candidate_label == row["expected_label"]

        candidate_cause = baseline_cause
        if baseline_cause == "classification_failure" and candidate_ok:
            candidate_cause = "success"
        elif baseline_cause == "success" and not candidate_ok:
            candidate_cause = "classification_failure"
        row.update(
            {
                "baseline_production_cause": baseline_cause,
                "resolver_status": resolver_status,
                "resolver_applied": resolver_applied,
                "version_factor_changed": version_factor_changed,
                "resolver_candidate_label": candidate_label,
                "resolver_candidate_classification_ok": candidate_ok,
                "resolver_candidate_cause": candidate_cause,
            }
        )
        ledger.append(row)

    missing = set(resolver_records) - seen_resolver_ids
    if missing:
        raise ValueError(
            f"130問のbaselineにresolver対象がありません: {sorted(missing)}"
        )

    baseline_counts = Counter(row["baseline_production_cause"] for row in ledger)
    candidate_counts = Counter(row["resolver_candidate_cause"] for row in ledger)
    improvements = sorted(
        row["id"]
        for row in ledger
        if not row["previous_decision_classification_ok"]
        and row["resolver_candidate_classification_ok"]
    )
    regressions = sorted(
        row["id"]
        for row in ledger
        if row["previous_decision_classification_ok"]
        and not row["resolver_candidate_classification_ok"]
    )
    severe_regressions = sorted(
        row["id"]
        for row in ledger
        if row["expected_label"] in {"判断要", "文書不足"}
        and row["previous_decision_classification_ok"]
        and not row["resolver_candidate_classification_ok"]
    )
    resolver_rows = [row for row in ledger if row["id"] in resolver_records]
    summary = {
        "total": len(ledger),
        "baseline_primary_causes": dict(sorted(baseline_counts.items())),
        "candidate_primary_causes": dict(sorted(candidate_counts.items())),
        "baseline_classification_correct": sum(
            row["previous_decision_classification_ok"] for row in ledger
        ),
        "candidate_classification_correct": sum(
            row["resolver_candidate_classification_ok"] for row in ledger
        ),
        "classification_improvements": improvements,
        "classification_regressions": regressions,
        "severe_label_regressions": severe_regressions,
        "resolver_call_count": len(resolver_rows),
        "resolver_applied_count": sum(row["resolver_applied"] for row in resolver_rows),
        "version_factor_changed_count": sum(
            row["version_factor_changed"] for row in resolver_rows
        ),
        "resolver_statuses": dict(
            sorted(Counter(row["resolver_status"] for row in resolver_rows).items())
        ),
        "gate": {
            "primary_failure_count_reduced": sum(candidate_counts.values())
            == sum(baseline_counts.values())
            and candidate_counts["classification_failure"]
            < baseline_counts["classification_failure"],
            "no_classification_regressions": not regressions,
            "no_severe_label_regressions": not severe_regressions,
            "passed": (
                candidate_counts["classification_failure"]
                < baseline_counts["classification_failure"]
                and not regressions
                and not severe_regressions
            ),
        },
    }
    return {"summary": summary, "ledger": ledger}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-analysis", type=Path, required=True)
    parser.add_argument("--text-records", type=Path, required=True)
    parser.add_argument("--resolver-records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"結果は上書きしません: {args.output}")
    result = analyze(
        _read_json(args.baseline_analysis),
        _read_jsonl(args.text_records, "question_id"),
        _read_jsonl(args.resolver_records, "question_id"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
