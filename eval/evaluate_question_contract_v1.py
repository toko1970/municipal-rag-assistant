"""Run bounded Gate B1 evaluation for Question Contract v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME
from eval.evaluate_visual_answers import token_cost_usd
from src.classification_contract_v2 import parse_question_contract_v2
from src.llm_provider import GeminiProvider
from src.query_service import load_schema
from src.query_service_v2 import (
    QUESTION_CONTRACT_PROMPT_VERSION,
    build_question_contract_prompt,
)


DEFAULT_CASES = BASE_DIR / "eval/question_contract_v1_mechanism_cases.json"
SCHEMA_PATH = BASE_DIR / "design/schemas/question-contract-v1.schema.json"
EXPECTED_CALLS = 18
MAX_COST_USD = 0.05
RESERVE_USD_PER_CALL = 0.002
SCORING_VERSION = "question-contract-mechanism-score-v1.1"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_dataset(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    cases = dataset.get("cases")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CALLS:
        raise ValueError(f"B1 datasetは{EXPECTED_CALLS}件で固定します")
    if dataset.get("case_count") != len(cases):
        raise ValueError("case_countが一致しません")
    if dataset.get("slice_counts") != {
        "over_abstention": 9,
        "dangerous_assertion": 3,
        "control": 6,
    }:
        raise ValueError("B1 slice件数が固定値と一致しません")
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case_idが重複しています")
    return cases


def _facet_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return actual.get("answer_type") == expected["answer_type"] and all(
        re.search(pattern, str(actual.get("requirement", "")), flags=re.IGNORECASE)
        for pattern in expected["requirement_patterns"]
    )


def score_contract(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected_facets"]
    actual = response.get("requested_facets", [])
    unused = set(range(len(actual)))
    matches: list[int | None] = []
    for expected_facet in expected:
        match = next(
            (
                index
                for index in sorted(unused)
                if _facet_matches(expected_facet, actual[index])
            ),
            None,
        )
        matches.append(match)
        if match is not None:
            unused.remove(match)
    facet_count_ok = len(actual) == len(expected)
    facets_ok = facet_count_ok and all(index is not None for index in matches)
    fact_text = "\n".join(
        str(row.get("text", "")) for row in response.get("input_facts", [])
    )
    input_pattern_results = {
        pattern: bool(re.search(pattern, fact_text, flags=re.IGNORECASE))
        for pattern in case["required_input_patterns"]
    }
    input_facts_ok = all(input_pattern_results.values())
    return {
        "facet_count_ok": facet_count_ok,
        "facets_ok": facets_ok,
        "facet_matches": matches,
        "input_facts_ok": input_facts_ok,
        "input_pattern_results": input_pattern_results,
        "contract_ok": facets_ok and input_facts_ok,
    }


def _summary(records: list[dict[str, Any]], total_cases: int) -> dict[str, Any]:
    completed = [row for row in records if row["error"] is None]
    by_slice = {}
    for name in ("over_abstention", "dangerous_assertion", "control"):
        rows = [row for row in completed if row["slice"] == name]
        by_slice[name] = {
            "completed": len(rows),
            "contract_ok": sum(row["score"]["contract_ok"] for row in rows),
            "facets_ok": sum(row["score"]["facets_ok"] for row in rows),
            "input_facts_ok": sum(row["score"]["input_facts_ok"] for row in rows),
        }
    contract_ok = sum(row["score"]["contract_ok"] for row in completed)
    passed = len(completed) == total_cases and contract_ok == total_cases
    return {
        "case_count": total_cases,
        "attempted": len(records),
        "completed": len(completed),
        "error_count": len(records) - len(completed),
        "contract_ok": contract_ok,
        "by_slice": by_slice,
        "gate": {
            "passed": passed,
            "rule": "18/18 contract_ok; exact facets and required question facts",
        },
        "stop_reason": (
            "COMPLETED"
            if len(records) == total_cases and not (len(records) - len(completed))
            else "FAIL_FAST"
        ),
    }


def run(
    *,
    dataset_path: Path,
    output_dir: Path,
    max_logical_external_calls: int,
    max_cost_usd: float,
    provider=None,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"結果は上書きしません: {output_dir}")
    if max_logical_external_calls != EXPECTED_CALLS:
        raise ValueError(f"logical external call上限は{EXPECTED_CALLS}で固定します")
    if not EXPECTED_CALLS * RESERVE_USD_PER_CALL <= max_cost_usd <= MAX_COST_USD:
        raise ValueError(f"cost上限は予約額以上US${MAX_COST_USD:.2f}以下です")

    dataset = _read_json(dataset_path)
    cases = validate_dataset(dataset)
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "run_manifest.json"
    records_path = output_dir / "records.jsonl"
    summary_path = output_dir / "summary.json"
    dataset_snapshot_path = output_dir / "dataset_snapshot.json"
    shutil.copyfile(dataset_path, dataset_snapshot_path)
    manifest = {
        "experiment": "question-contract-v1-gate-b1",
        "status": "RUNNING",
        "started_at": datetime.now(UTC).isoformat(),
        "dataset_path": str(dataset_path.relative_to(BASE_DIR)),
        "dataset_sha256": _sha256(dataset_path),
        "dataset_snapshot_path": dataset_snapshot_path.name,
        "dataset_snapshot_sha256": _sha256(dataset_snapshot_path),
        "source_review_sha256": dataset["source_review_sha256"],
        "model": CLASSIFIER_MODEL_NAME,
        "prompt_version": QUESTION_CONTRACT_PROMPT_VERSION,
        "scoring_version": SCORING_VERSION,
        "schema_path": str(SCHEMA_PATH.relative_to(BASE_DIR)),
        "schema_sha256": _sha256(SCHEMA_PATH),
        "max_logical_external_calls": max_logical_external_calls,
        "max_cost_usd": max_cost_usd,
        "retry_count": 0,
        "sealed_holdout_accessed": False,
    }
    _write_json(manifest_path, manifest)

    provider = provider or GeminiProvider(CLASSIFIER_MODEL_NAME)
    schema = load_schema(SCHEMA_PATH)
    records: list[dict[str, Any]] = []
    input_tokens = 0
    output_tokens = 0
    for case in cases:
        if (
            token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_CALL
            > max_cost_usd
        ):
            raise RuntimeError("cost上限へ達する前にB1を完了できません")
        started = time.perf_counter()
        response = None
        error = None
        case_input = 0
        case_output = 0
        score = None
        try:
            result = provider.generate_structured(
                build_question_contract_prompt(case["question"]), schema
            )
            response = result.data
            case_input = result.input_tokens
            case_output = result.output_tokens
            parse_question_contract_v2(response)
            score = score_contract(case, response)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        input_tokens += case_input
        output_tokens += case_output
        records.append(
            {
                "case_id": case["case_id"],
                "scenario_id": case["scenario_id"],
                "variant_type": case["variant_type"],
                "slice": case["slice"],
                "question": case["question"],
                "response": response,
                "score": score,
                "input_tokens": case_input,
                "output_tokens": case_output,
                "estimated_cost_usd": token_cost_usd(case_input, case_output),
                "latency_seconds": time.perf_counter() - started,
                "error": error,
            }
        )
        _write_jsonl(records_path, records)
        if error:
            break

    summary = _summary(records, len(cases))
    summary.update(
        {
            "logical_external_calls": len(records),
            "max_logical_external_calls": max_logical_external_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
            "max_cost_usd": max_cost_usd,
        }
    )
    _write_json(summary_path, summary)
    manifest.update(
        {
            "status": "COMPLETED"
            if summary["stop_reason"] == "COMPLETED"
            else "FAILED",
            "completed_at": datetime.now(UTC).isoformat(),
            "logical_external_calls": len(records),
            "records_sha256": _sha256(records_path),
            "summary_sha256": _sha256(summary_path),
        }
    )
    _write_json(manifest_path, manifest)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    summary = run(
        dataset_path=args.dataset.resolve(),
        output_dir=args.output_dir.resolve(),
        max_logical_external_calls=args.max_logical_external_calls,
        max_cost_usd=args.max_cost_usd,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
