"""Evaluate a dedicated version resolver on fixed retrieved-evidence cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, TOP_K
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.compare_version_conflict_prompt import _answer_payload, _read_jsonl
from eval.evaluate_retrieved_text_regression import (
    DEFAULT_DOCUMENT_CACHE,
    DEFAULT_QUERY_CACHE,
    prepare_text_corpus,
)
from eval.evaluate_visual_answers import token_cost_usd
from src.answering import ClassificationFactors, derive_label
from src.llm_provider import GeminiProvider
from src.query_service import _evidence_payload, load_schema
from src.version_resolution import (
    build_version_resolution_prompt,
    parse_version_resolution,
)


DEFAULT_RECORDS = (
    BASE_DIR
    / "eval/results/retrieved_text_regression_e24d7d4_v2/evaluation/records.jsonl"
)
VERSION_SCHEMA = BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
PROMPT_VERSION = "version-resolution-v2"
RESERVE_USD_PER_CALL = 0.002

TARGET_IDS = {
    "Q121",
    "Q196",
    "Q201",
    "Q231",
    "Q281",
    "Q286",
    "Q416",
}
TRUE_CONFLICT_IDS = {"Q176"}
DIAGNOSTIC_IDS = {"Q291"}
SELECTED_IDS = TARGET_IDS | TRUE_CONFLICT_IDS | DIAGNOSTIC_IDS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_cases(records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    missing = SELECTED_IDS - set(records)
    if missing:
        raise ValueError(f"版解決対象がrecordsにありません: {sorted(missing)}")
    cases = []
    for question_id in sorted(SELECTED_IDS):
        case = records[question_id]
        if not case["classification_factors"]["version_conflict"]:
            raise ValueError(f"既存分類がversion conflictではありません: {question_id}")
        if question_id in TARGET_IDS:
            role = "target_resolved_version"
            expected_conflict = False
        elif question_id in TRUE_CONFLICT_IDS:
            role = "control_true_version_conflict"
            expected_conflict = True
        else:
            role = "diagnostic_retrieval_failure"
            expected_conflict = False
        cases.append(
            {**case, "role": role, "expected_version_conflict": expected_conflict}
        )
    return cases


def compose_label(case: dict[str, Any], version_conflict: bool) -> str:
    factors = dict(case["classification_factors"])
    factors["version_conflict"] = version_conflict
    return derive_label(ClassificationFactors(**factors))


def summarize(results: list[dict[str, Any]], case_count: int) -> dict[str, Any]:
    completed = [record for record in results if record["error"] is None]
    targets = [
        record for record in completed if record["role"] == "target_resolved_version"
    ]
    controls = [
        record
        for record in completed
        if record["role"] == "control_true_version_conflict"
    ]
    target_correct = sum(record["resolver_correct"] for record in targets)
    control_correct = sum(record["resolver_correct"] for record in controls)
    error_count = sum(record["error"] is not None for record in results)
    return {
        "case_count": case_count,
        "logical_external_call_count": len(results),
        "completed_count": len(completed),
        "error_count": error_count,
        "target_correct": target_correct,
        "target_count": len(TARGET_IDS),
        "true_conflict_control_correct": control_correct,
        "true_conflict_control_count": len(TRUE_CONFLICT_IDS),
        "diagnostic_correct": sum(
            record["resolver_correct"]
            for record in completed
            if record["role"] == "diagnostic_retrieval_failure"
        ),
        "stop_reason": "PROVIDER_ERROR_FAIL_FAST" if error_count else "COMPLETED",
        "gate": {
            "passed": (
                error_count == 0
                and target_correct == len(TARGET_IDS)
                and control_correct == len(TRUE_CONFLICT_IDS)
            )
        },
    }


def run_evaluation(
    *,
    records_path: Path,
    query_cache: Path,
    document_cache: Path,
    output_dir: Path,
    max_logical_external_calls: int,
    max_cost_usd: float,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"結果は上書きしません: {output_dir}")
    cases = select_cases(_read_jsonl(records_path))
    if max_logical_external_calls != len(cases):
        raise ValueError(f"logical external call上限は{len(cases)}で固定します")
    if max_cost_usd < len(cases) * RESERVE_USD_PER_CALL:
        raise ValueError("cost上限が全callの予約額を下回っています")

    index = prepare_text_corpus(document_cache)
    query_vectors = load_baseline_query_vectors(query_cache, cases)
    evidence_by_id = {}
    for case in cases:
        hits = index.search(query_vectors[case["question"]], TOP_K)
        expected_ids = [item["element_id"] for item in case["retrieved"]]
        actual_ids = [str(hit.element.id) for hit in hits]
        if actual_ids != expected_ids:
            raise ValueError(f"保存済み検索結果を再現できません: {case['question_id']}")
        evidence_by_id[case["question_id"]] = _evidence_payload(hits)

    output_dir.mkdir(parents=True)
    records_output = output_dir / "records.jsonl"
    manifest = {
        "experiment": "version-resolver-v2",
        "records_path": str(records_path.relative_to(BASE_DIR)),
        "records_sha256": _sha256(records_path),
        "query_cache_sha256": _sha256(query_cache),
        "document_cache_sha256": _sha256(document_cache),
        "schema_sha256": _sha256(VERSION_SCHEMA),
        "model": CLASSIFIER_MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
        "case_count": len(cases),
        "max_logical_external_calls": max_logical_external_calls,
        "max_cost_usd": max_cost_usd,
        "retry_count": 0,
        "sealed_holdout_accessed": False,
        "production_integrated": False,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    provider = GeminiProvider(CLASSIFIER_MODEL_NAME)
    schema = load_schema(VERSION_SCHEMA)
    results = []
    input_tokens = 0
    output_tokens = 0
    for case in cases:
        if (
            token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_CALL
            > max_cost_usd
        ):
            raise RuntimeError("cost上限へ達する前に評価を完了できません")
        error = None
        response_data = None
        resolver_correct = False
        composed_label = None
        case_input = 0
        case_output = 0
        try:
            response = provider.generate_structured(
                build_version_resolution_prompt(
                    case["question"],
                    evidence_by_id[case["question_id"]],
                    _answer_payload(case),
                ),
                schema,
            )
            response_data = response.data
            case_input = response.input_tokens
            case_output = response.output_tokens
            resolution = parse_version_resolution(response_data)
            retrieved_ids = {
                item["element_id"] for item in evidence_by_id[case["question_id"]]
            }
            if (
                not {str(item) for item in resolution.evidence_element_ids}
                <= retrieved_ids
            ):
                raise ValueError("resolverが取得外の根拠IDを返しました")
            resolver_correct = (
                resolution.version_conflict == case["expected_version_conflict"]
            )
            composed_label = compose_label(case, resolution.version_conflict)
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"
        input_tokens += case_input
        output_tokens += case_output
        result = {
            "question_id": case["question_id"],
            "role": case["role"],
            "expected_version_conflict": case["expected_version_conflict"],
            "resolver_version_conflict": (
                response_data.get("version_conflict") if response_data else None
            ),
            "resolver_correct": resolver_correct,
            "expected_label": case["expected_label"],
            "composed_label": composed_label,
            "composed_label_correct": composed_label == case["expected_label"],
            "response": response_data,
            "input_tokens": case_input,
            "output_tokens": case_output,
            "error": error,
        }
        results.append(result)
        with records_output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        if error:
            break

    summary = summarize(results, len(cases))
    summary.update(
        {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
            "max_cost_usd": max_cost_usd,
        }
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    summary = run_evaluation(
        records_path=args.records.resolve(),
        query_cache=args.query_cache.resolve(),
        document_cache=args.document_cache.resolve(),
        output_dir=args.output_dir.resolve(),
        max_logical_external_calls=args.max_logical_external_calls,
        max_cost_usd=args.max_cost_usd,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
