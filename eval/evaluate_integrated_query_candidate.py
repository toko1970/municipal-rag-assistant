"""Evaluate the production-integrated candidate on decomposition-only questions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME, TOP_K
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.compare_embedding_models import load_or_create_vectors
from eval.embedding_profiles import PROFILES
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_models import load_questions
from eval.evaluate_query_decomposition_answers import (
    _provider,
    _provider_error,
    _scenario_logical_calls,
)
from eval.evaluate_retrieved_text_regression import (
    _retrieval_outcome,
    prepare_text_corpus,
)
from eval.evaluate_temporal_generation_candidate import _attempt_diagnostics
from eval.evaluate_visual_answers import token_cost_usd
from src.query_decomposition import DecomposedVectorIndex, decompose_query
from src.query_service import answer_question, load_schema
from src.temporal_evidence import (
    TEMPORAL_GENERATION_PROMPT_VERSION,
    build_temporal_generation_prompt,
)


ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
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
TARGET_IDS = ("Q131", "Q156", "Q436")
CONTROL_IDS = ("Q441", "Q446")
SELECTED_IDS = (*TARGET_IDS, *CONTROL_IDS)
RESERVE_USD_PER_SCENARIO = 0.005
MAX_CALLS_PER_SCENARIO = 3
CONTENT_RULES = {
    "Q131": (r"1[.]5\s*km", r"実際に通勤|実通勤", r"届", r"10日以内"),
    "Q156": (r"支給停止|停止", r"住所変更届"),
    "Q436": (r"支給停止|停止", r"住所変更届", r"14日以内"),
    "Q441": (r"一括", r"分割", r"口座変更届", r"口座情報.*確認|通帳|キャッシュカード"),
    "Q446": (
        r"本人名義",
        r"15[,.]?000円を超",
        r"住居届",
        r"契約書",
        r"支払.*確認|領収書|振込",
        r"30日以内",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _content_ok(question_id: str, answer: str) -> bool:
    return all(re.search(pattern, answer) for pattern in CONTENT_RULES[question_id])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--subquery-cache", type=Path, default=DEFAULT_SUBQUERY_CACHE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_cost_usd < len(SELECTED_IDS) * RESERVE_USD_PER_SCENARIO:
        raise ValueError("費用上限が5シナリオの予約額を下回っています")

    all_questions = load_questions(args.input, "formal")
    by_id = {row["question_id"]: row for row in all_questions}
    questions = [by_id[question_id] for question_id in SELECTED_IDS]
    original_vectors = load_baseline_query_vectors(args.query_cache, all_questions)
    subqueries = list(
        dict.fromkeys(
            subquery
            for row in all_questions
            for subquery in decompose_query(row["question"])
            if decompose_query(row["question"]) != [row["question"]]
        )
    )
    profile = PROFILES["gemini-embedding-001"]
    subquery_ids = [
        f"query:{hashlib.sha256(query.encode()).hexdigest()}" for query in subqueries
    ]

    def cache_miss(_texts: list[str]) -> list[list[float]]:
        raise ValueError("subquery cacheがありません。APIで暗黙生成しません")

    subquery_vectors, cache_hit, _ = load_or_create_vectors(
        args.subquery_cache,
        profile=profile,
        kind="query-decomposition-v1",
        ids=subquery_ids,
        texts=subqueries,
        embed=cache_miss,
    )
    if not cache_hit:
        raise AssertionError("subquery cacheを再利用できませんでした")
    vectors = {
        **original_vectors,
        **dict(zip(subqueries, subquery_vectors, strict=True)),
    }
    base_index = prepare_text_corpus(args.document_cache)
    args.output_dir.mkdir(parents=True)
    records_path = args.output_dir / "records.jsonl"
    manifest = {
        "experiment": "production-integrated-query-candidate-v1",
        "dataset_sha256": _sha256(args.input),
        "query_cache_sha256": _sha256(args.query_cache),
        "subquery_cache_sha256": _sha256(args.subquery_cache),
        "document_cache_sha256": _sha256(args.document_cache),
        "selected_ids": list(SELECTED_IDS),
        "target_ids": list(TARGET_IDS),
        "control_ids": list(CONTROL_IDS),
        "content_rules": CONTENT_RULES,
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "top_k": TOP_K,
        "generation_prompt_version": TEMPORAL_GENERATION_PROMPT_VERSION,
        "max_logical_external_calls": len(SELECTED_IDS) * MAX_CALLS_PER_SCENARIO,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "sealed_holdout_accessed": False,
        "production_deployed": False,
    }
    _write_json(args.output_dir / "run_manifest.json", manifest)

    generator = _provider(LLM_MODEL_NAME)
    classifier = _provider(CLASSIFIER_MODEL_NAME)
    resolver = _provider(CLASSIFIER_MODEL_NAME)
    records: list[dict[str, Any]] = []
    input_tokens = 0
    output_tokens = 0
    logical_calls = 0
    stop_reason = "COMPLETED"

    for row in questions:
        if (
            token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_SCENARIO
            > args.max_cost_usd
        ):
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
                generation_prompt_builder=build_temporal_generation_prompt,
                generation_prompt_version=TEMPORAL_GENERATION_PROMPT_VERSION,
            )
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"

        resolver_data = result.get("version_resolution", {}) if result else {}
        generation_input = int(logger.generation.get("input_tokens", 0))
        generation_output = int(logger.generation.get("output_tokens", 0))
        classification_input = int(logger.classification.get("input_tokens", 0))
        classification_output = int(logger.classification.get("output_tokens", 0))
        resolver_input = int(resolver_data.get("input_tokens", 0))
        resolver_output = int(resolver_data.get("output_tokens", 0))
        scenario_input = generation_input + classification_input + resolver_input
        scenario_output = generation_output + classification_output + resolver_output
        input_tokens += scenario_input
        output_tokens += scenario_output
        logical_calls += _scenario_logical_calls(logger, result)

        retrieval = _retrieval_outcome(row, logger)
        answer = result.get("answer", "") if result else ""
        classification_ok = bool(result) and (
            result.get("answer_label") == row["expected_answer_type"]
        )
        content_ok = bool(result) and _content_ok(row["question_id"], answer)
        support_ok = bool(result) and bool(
            (logger.classification.get("factors") or {}).get("answer_fully_supported")
        )
        composite_ok = bool(retrieval["retrieval_ok"]) and all(
            (classification_ok, content_ok, support_ok)
        )
        record = {
            "question_id": row["question_id"],
            "role": "target" if row["question_id"] in TARGET_IDS else "control",
            "question": row["question"],
            **retrieval,
            "answer": answer,
            "predicted_label": result.get("answer_label") if result else None,
            "classification_ok": classification_ok,
            "content_ok": content_ok,
            "support_ok": support_ok,
            "composite_ok": composite_ok,
            "input_tokens": scenario_input,
            "output_tokens": scenario_output,
            "estimated_cost_usd": token_cost_usd(scenario_input, scenario_output),
            "version_resolution": resolver_data,
            **_attempt_diagnostics(logger),
            "elapsed_seconds": time.perf_counter() - started,
            "error": error or None,
        }
        records.append(record)
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(
            f"{row['question_id']}: retrieval={retrieval['retrieval_ok']} "
            f"classification={classification_ok} content={content_ok} "
            f"support={support_ok} error={error or 'none'}"
        )
        if error and _provider_error(error):
            stop_reason = "PROVIDER_ERROR_FAIL_FAST"
            break

    if logical_calls > len(SELECTED_IDS) * MAX_CALLS_PER_SCENARIO:
        raise RuntimeError("logical external call上限を超えました")
    completed = [record for record in records if record["error"] is None]
    improvement_count = sum(
        record["composite_ok"]
        for record in completed
        if record["question_id"] in TARGET_IDS
    )
    control_regressions = [
        record["question_id"]
        for record in completed
        if record["question_id"] in CONTROL_IDS and not record["composite_ok"]
    ]
    summary = {
        "scenario_count": len(SELECTED_IDS),
        "completed_count": len(completed),
        "target_improvement_count": improvement_count,
        "target_count": len(TARGET_IDS),
        "control_regression_ids": control_regressions,
        "gate_passed": (
            stop_reason == "COMPLETED"
            and len(completed) == len(SELECTED_IDS)
            and improvement_count >= 2
            and not control_regressions
        ),
        "logical_external_calls": logical_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": args.max_cost_usd,
        "stop_reason": stop_reason,
        "sealed_holdout_accessed": False,
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
