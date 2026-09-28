"""Evaluate deterministic query triggers on frozen paraphrase and boundary cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from config import BASE_DIR
from src.contracts import SearchHit
from src.query_decomposition import decompose_query
from src.temporal_evidence import POLICY_DOMAINS, analyze_temporal_evidence


DEFAULT_INPUT = BASE_DIR / "eval/query_trigger_robustness_cases.json"
RULES = {"none", "move_commute_stop", "birth_start_deadline"}


def _decomposition_rule(question: str) -> str:
    subqueries = decompose_query(question)
    if subqueries == [question]:
        return "none"
    joined = " ".join(subqueries)
    if "住所変更届" in joined and "通勤手当" in joined:
        return "move_commute_stop"
    if "扶養親族変更届" in joined and "扶養手当" in joined:
        return "birth_start_deadline"
    return "unknown"


def _revision_hit(domain: str, value: int) -> SearchHit:
    element = SimpleNamespace(
        id=UUID(int=value),
        metadata={
            "見出し1": f"{domain}の改正",
            "見出し2": "改正後",
            "effective_date": "2025-10-01",
            "document_role": "revision_history",
        },
        content=f"{domain}の改正後の規定。",
    )
    return SearchHit(element=element, score=1.0, rank=value)


def _temporal_domains(question: str) -> list[str]:
    hits = [_revision_hit(domain, index) for index, domain in enumerate(POLICY_DOMAINS, 1)]
    result = analyze_temporal_evidence(question, hits)
    return list(result.applicable_domains) if result else []


def _binary_metrics(records: list[dict], expected_key: str, actual_key: str) -> dict:
    true_positive = sum(bool(row[expected_key]) and bool(row[actual_key]) for row in records)
    false_positive = sum(not row[expected_key] and bool(row[actual_key]) for row in records)
    false_negative = sum(bool(row[expected_key]) and not row[actual_key] for row in records)
    true_negative = sum(not row[expected_key] and not row[actual_key] for row in records)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": precision,
        "recall": recall,
    }


def evaluate(payload: dict) -> tuple[list[dict], dict]:
    records = []
    for case in payload["cases"]:
        actual_rule = _decomposition_rule(case["question"])
        actual_domains = _temporal_domains(case["question"])
        expected_rule = case["expected_decomposition"]
        expected_domains = case["expected_temporal_domains"]
        records.append(
            {
                **case,
                "actual_decomposition": actual_rule,
                "actual_temporal_domains": actual_domains,
                "decomposition_ok": actual_rule == expected_rule,
                "temporal_ok": actual_domains == expected_domains,
                "expected_decomposition_applied": expected_rule != "none",
                "actual_decomposition_applied": actual_rule != "none",
                "expected_temporal_applied": bool(expected_domains),
                "actual_temporal_applied": bool(actual_domains),
            }
        )
    summary = {
        "dataset_version": payload["dataset_version"],
        "case_count": len(records),
        "family_counts": dict(Counter(row["family"] for row in records)),
        "decomposition": {
            **_binary_metrics(
                records,
                "expected_decomposition_applied",
                "actual_decomposition_applied",
            ),
            "exact_match_count": sum(row["decomposition_ok"] for row in records),
        },
        "temporal_guidance": {
            **_binary_metrics(
                records,
                "expected_temporal_applied",
                "actual_temporal_applied",
            ),
            "exact_match_count": sum(row["temporal_ok"] for row in records),
        },
        "failed_case_ids": [
            row["id"]
            for row in records
            if not row["decomposition_ok"] or not row["temporal_ok"]
        ],
        "external_api_calls": 0,
        "sealed_holdout_accessed": False,
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    records, summary = evaluate(payload)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    manifest = {
        "experiment": "query-trigger-robustness-v1",
        "dataset_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "frozen_before_candidate_change": payload["frozen_before_candidate_change"],
        "external_api_calls": 0,
        "sealed_holdout_accessed": False,
    }
    for name, value in (("run_manifest.json", manifest), ("summary.json", summary)):
        (args.output_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
