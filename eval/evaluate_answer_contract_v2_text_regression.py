"""Evaluate answer-contract v2 on the 100-question text development split."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME, TOP_K
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.embedding_profiles import PROFILES
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_integrated_query_candidate import (
    _attempt_diagnostics,
    _provider,
    _provider_error,
    _scenario_logical_calls,
)
from eval.evaluate_models import load_questions
from eval.evaluate_retrieved_text_regression import (
    _retrieval_outcome,
    prepare_text_corpus,
)
from eval.evaluate_visual_answers import token_cost_usd
from eval.query_decomposition_cache import load_cached_subquery_vectors
from src.query_decomposition import DecomposedVectorIndex, decompose_query
from src.query_service import (
    CLASSIFICATION_PROMPT_V2_VERSION,
    answer_question,
    build_classification_prompt_v2,
    load_schema,
)
from src.temporal_evidence import (
    ANSWER_CONTRACT_V2_PROMPT_VERSION,
    build_answer_contract_v2_prompt,
)


ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v2.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
VERSION_SCHEMA = BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
DEFAULT_INPUT = BASE_DIR / "eval/evaluation_questions_500.csv"
DEFAULT_QUERY_CACHE = BASE_DIR / ".eval_cache/large_formal_query_vectors.json"
DEFAULT_SUBQUERY_CACHE = (
    BASE_DIR / ".eval_cache/query_decomposition_gemini_001_queries.json"
)
DEFAULT_DOCUMENT_CACHE = (
    BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
)
MAX_SCENARIOS = 100
MAX_CALLS_PER_SCENARIO = 3
MAX_LOGICAL_EXTERNAL_CALLS = MAX_SCENARIOS * MAX_CALLS_PER_SCENARIO
RESERVE_USD_PER_SCENARIO = 0.0014


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _subquery_vectors(
    questions: list[dict[str, str]], cache_path: Path
) -> dict[str, list[float]]:
    subqueries = list(
        dict.fromkeys(
            subquery
            for row in questions
            for subquery in decompose_query(row["question"])
            if decompose_query(row["question"]) != [row["question"]]
        )
    )
    profile = PROFILES["gemini-embedding-001"]
    ids = [
        f"query:{hashlib.sha256(query.encode()).hexdigest()}" for query in subqueries
    ]
    vectors = load_cached_subquery_vectors(
        cache_path,
        profile=profile,
        kind="query-decomposition-v1",
        ids=ids,
    )
    return dict(zip(subqueries, vectors, strict=True))


def _classification_ok(row: dict[str, str], result: dict | None) -> bool:
    return bool(result) and result.get("answer_label") == row["expected_answer_type"]


def _record(
    *,
    row: dict[str, str],
    logger: EvaluationLogger,
    result: dict | None,
    error: str,
    elapsed_seconds: float,
) -> dict[str, Any]:
    resolver = result.get("version_resolution", {}) if result else {}
    generation_input = int(logger.generation.get("input_tokens", 0))
    generation_output = int(logger.generation.get("output_tokens", 0))
    classification_input = int(logger.classification.get("input_tokens", 0))
    classification_output = int(logger.classification.get("output_tokens", 0))
    resolver_input = int(resolver.get("input_tokens", 0))
    resolver_output = int(resolver.get("output_tokens", 0))
    input_tokens = generation_input + classification_input + resolver_input
    output_tokens = generation_output + classification_output + resolver_output
    generated = logger.generation.get("response_data") or {}
    retrieval = _retrieval_outcome(row, logger)
    return {
        "question_id": row["question_id"],
        "question": row["question"],
        "difficulty": row["difficulty"],
        "expected_label": row["expected_answer_type"],
        "expected_answer_key": row["expected_answer_key"],
        **retrieval,
        "predicted_label": result.get("answer_label") if result else None,
        "answer_status": result.get("answer_status") if result else None,
        "invariant_code": result.get("invariant_code") if result else None,
        "classification_ok": _classification_ok(row, result),
        "classification_factors": logger.classification.get("factors"),
        "answer": result.get("answer", "") if result else "",
        "claims": result.get("claims", []) if result else generated.get("claims", []),
        "missing_conditions": generated.get("missing_conditions", []),
        "date_calculations": generated.get("date_calculations", []),
        "content_review_status": "pending" if result else "blocked_by_error",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": token_cost_usd(input_tokens, output_tokens),
        "logical_external_calls": _scenario_logical_calls(logger, result),
        "version_resolution": resolver,
        **_attempt_diagnostics(logger),
        "elapsed_seconds": elapsed_seconds,
        "error": error or None,
    }


def _summary(
    records: list[dict[str, Any]], *, stop_reason: str, max_cost_usd: float
) -> dict[str, Any]:
    completed = [record for record in records if record["error"] is None]
    return {
        "scenario_count": MAX_SCENARIOS,
        "record_count": len(records),
        "completed_count": len(completed),
        "error_count": len(records) - len(completed),
        "retrieval_applicable_count": sum(
            bool(record["retrieval_applicable"]) for record in completed
        ),
        "retrieval_correct": sum(
            record["retrieval_ok"] is True for record in completed
        ),
        "classification_correct": sum(
            bool(record["classification_ok"]) for record in completed
        ),
        "semantic_success": sum(
            record["answer_status"] == "SUCCESS" for record in completed
        ),
        "content_review_pending": len(completed),
        "logical_external_calls": sum(
            int(record["logical_external_calls"]) for record in records
        ),
        "input_tokens": sum(int(record["input_tokens"]) for record in records),
        "output_tokens": sum(int(record["output_tokens"]) for record in records),
        "estimated_cost_usd": sum(float(record["cost_usd"]) for record in records),
        "max_cost_usd": max_cost_usd,
        "stop_reason": stop_reason,
        "sealed_holdout_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--subquery-cache", type=Path, default=DEFAULT_SUBQUERY_CACHE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_logical_external_calls > MAX_LOGICAL_EXTERNAL_CALLS:
        raise ValueError("logical external call上限は300です")
    if args.max_cost_usd < MAX_SCENARIOS * RESERVE_USD_PER_SCENARIO:
        raise ValueError("費用上限が100問の安全予約額を下回っています")

    questions = load_questions(args.input, "formal")
    if len(questions) != MAX_SCENARIOS:
        raise ValueError(f"formal質問は100件必要です: {len(questions)}")
    original_vectors = load_baseline_query_vectors(args.query_cache, questions)
    vectors = {**original_vectors, **_subquery_vectors(questions, args.subquery_cache)}
    base_index = prepare_text_corpus(args.document_cache)
    args.output_dir.mkdir(parents=True)
    records_path = args.output_dir / "records.jsonl"
    manifest = {
        "experiment": "answer-contract-v2-text-regression-v1",
        "dataset_sha256": _sha256(args.input),
        "query_cache_sha256": _sha256(args.query_cache),
        "subquery_cache_sha256": _sha256(args.subquery_cache),
        "document_cache_sha256": _sha256(args.document_cache),
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "answer_schema": str(ANSWER_SCHEMA.relative_to(BASE_DIR)),
        "generation_prompt_version": ANSWER_CONTRACT_V2_PROMPT_VERSION,
        "classification_prompt_version": CLASSIFICATION_PROMPT_V2_VERSION,
        "query_decomposition": "query-decomposition-v1",
        "version_resolver": "version-resolution-v2",
        "top_k": TOP_K,
        "scenario_count": len(questions),
        "max_logical_external_calls": args.max_logical_external_calls,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "reserve_usd_per_scenario": RESERVE_USD_PER_SCENARIO,
        "stop_conditions": ["provider error", "cost reserve", "call limit"],
        "sealed_holdout_accessed": False,
        "production_deployed": False,
    }
    _write_json(args.output_dir / "run_manifest.json", manifest)

    generator = _provider(LLM_MODEL_NAME)
    classifier = _provider(CLASSIFIER_MODEL_NAME)
    resolver = _provider(CLASSIFIER_MODEL_NAME)
    records: list[dict[str, Any]] = []
    stop_reason = "COMPLETED"
    for row in questions:
        used_calls = sum(int(record["logical_external_calls"]) for record in records)
        used_cost = sum(float(record["cost_usd"]) for record in records)
        if used_calls + MAX_CALLS_PER_SCENARIO > args.max_logical_external_calls:
            stop_reason = "CALL_LIMIT_REACHED"
            break
        if used_cost + RESERVE_USD_PER_SCENARIO > args.max_cost_usd:
            stop_reason = "COST_LIMIT_REACHED"
            break
        logger = EvaluationLogger()
        result = None
        error = ""
        started = time.perf_counter()
        index = DecomposedVectorIndex(
            question=row["question"],
            base_index=base_index,
            embed_query=lambda query: vectors[query],
        )
        try:
            result = answer_question(
                row["question"],
                embed_query=lambda query: original_vectors[query],
                vector_index=index,
                generator=generator,
                classifier=classifier,
                version_resolver=resolver,
                event_logger=logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                version_resolution_schema=load_schema(VERSION_SCHEMA),
                top_k=TOP_K,
                generation_prompt_builder=build_answer_contract_v2_prompt,
                generation_prompt_version=ANSWER_CONTRACT_V2_PROMPT_VERSION,
                classification_prompt_builder=build_classification_prompt_v2,
                classification_prompt_version=CLASSIFICATION_PROMPT_V2_VERSION,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        record = _record(
            row=row,
            logger=logger,
            result=result,
            error=error,
            elapsed_seconds=time.perf_counter() - started,
        )
        records.append(record)
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        print(
            f"{row['question_id']}: retrieval={record['retrieval_ok']} "
            f"classification={record['classification_ok']} "
            f"status={record['answer_status']} error={error or 'none'}"
        )
        if error:
            stop_reason = (
                "PROVIDER_ERROR_FAIL_FAST"
                if _provider_error(error)
                else "CANDIDATE_ERROR_FAIL_FAST"
            )
            break

    summary = _summary(records, stop_reason=stop_reason, max_cost_usd=args.max_cost_usd)
    if summary["logical_external_calls"] > args.max_logical_external_calls:
        raise RuntimeError("logical external call上限を超えました")
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if stop_reason == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
