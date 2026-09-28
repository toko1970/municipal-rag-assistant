"""Evaluate query decomposition plus deterministic pre-generation version guidance."""

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
    QuestionAwareIndex,
    _provider,
    _provider_error,
    _scenario_logical_calls,
)
from eval.evaluate_retrieved_text_regression import prepare_text_corpus
from eval.evaluate_visual_answers import token_cost_usd
from eval.query_decomposition import decompose_query
from src.query_service import answer_question, build_generation_prompt, load_schema
from src.temporal_evidence import temporal_prompt_instruction


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
TARGET_ID = "Q291"
CONTROL_IDS = ("Q421", "Q426", "Q431")
SELECTED_IDS = (TARGET_ID, *CONTROL_IDS)
MAX_LOGICAL_EXTERNAL_CALLS = 12
RESERVE_USD_PER_SCENARIO = 0.005
CONTENT_RULES = {
    "Q291": {
        "required": (r"(認定された月|認定月)", r"15日以内"),
        "rejected": (r"翌月",),
    },
    "Q421": {
        "required": (r"2\s*km", r"1[.]5\s*km"),
        "rejected": (),
    },
    "Q426": {
        "required": (r"16[,.]?000円", r"15[,.]?000円"),
        "rejected": (),
    },
    "Q431": {
        "required": (r"翌月", r"(認定された月|認定月)"),
        "rejected": (),
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _content_ok(question_id: str, answer: str) -> bool:
    rule = CONTENT_RULES[question_id]
    return all(re.search(pattern, answer) for pattern in rule["required"]) and not any(
        re.search(pattern, answer) for pattern in rule["rejected"]
    )


def build_temporal_generation_prompt(question: str, hits: list, visual_assets) -> str:
    instruction = temporal_prompt_instruction(question, hits)
    base = build_generation_prompt(question, hits, visual_assets)
    if instruction is None:
        raise ValueError("評価対象に生成前の版適用情報を作成できません")
    return f"{instruction}\n{base}"


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
        raise ValueError("費用上限が4シナリオの予約額を下回っています")

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
    index = QuestionAwareIndex(
        prepare_text_corpus(args.document_cache), vectors, decompose=True
    )

    args.output_dir.mkdir(parents=True)
    records_path = args.output_dir / "records.jsonl"
    manifest = {
        "experiment": "pre-generation-temporal-guidance-v1",
        "dataset_sha256": _sha256(args.input),
        "query_cache_sha256": _sha256(args.query_cache),
        "subquery_cache_sha256": _sha256(args.subquery_cache),
        "document_cache_sha256": _sha256(args.document_cache),
        "target_id": TARGET_ID,
        "control_ids": list(CONTROL_IDS),
        "content_rules": CONTENT_RULES,
        "retrieval": "query decomposition when a deterministic rule matches; otherwise dense",
        "generation_candidate": "deterministic temporal guidance prepended to current prompt",
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "top_k": TOP_K,
        "max_logical_external_calls": MAX_LOGICAL_EXTERNAL_CALLS,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "sealed_holdout_accessed": False,
        "production_integrated": False,
    }
    _write_json(args.output_dir / "run_manifest.json", manifest)

    generator = _provider(LLM_MODEL_NAME)
    classifier = _provider(CLASSIFIER_MODEL_NAME)
    resolver = _provider(CLASSIFIER_MODEL_NAME)
    input_tokens = 0
    output_tokens = 0
    logical_calls = 0
    records = []
    stop_reason = "COMPLETED"

    for row in questions:
        if (
            token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_SCENARIO
            > args.max_cost_usd
        ):
            stop_reason = "COST_LIMIT_REACHED"
            break
        index.select_question(row["question"])
        logger = EvaluationLogger()
        result = None
        error = ""
        started = time.perf_counter()
        try:
            result = answer_question(
                row["question"],
                embed_query=lambda question: original_vectors[question],
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
                generation_prompt_version="answer-claims-v1+temporal-guidance-v1",
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

        answer = result.get("answer", "") if result else ""
        classification_ok = bool(result) and (
            result.get("answer_label") == row["expected_answer_type"]
        )
        content_ok = bool(result) and _content_ok(row["question_id"], answer)
        support_ok = bool(result) and (
            not result.get("claims")
            or bool(
                (logger.classification.get("factors") or {}).get(
                    "answer_fully_supported"
                )
            )
        )
        references = result.get("references", []) if result else []
        record = {
            "question_id": row["question_id"],
            "role": "target" if row["question_id"] == TARGET_ID else "control",
            "question": row["question"],
            "temporal_instruction": temporal_prompt_instruction(
                row["question"], logger.retrieval_hits
            ),
            "answer": answer,
            "predicted_label": result.get("answer_label") if result else None,
            "classification_ok": classification_ok,
            "content_ok": content_ok,
            "support_ok": support_ok,
            "composite_ok": classification_ok and content_ok and support_ok,
            "retrieved": [
                {
                    "rank": rank,
                    "document_id": item.get("document_id"),
                    "heading": item.get("heading"),
                }
                for rank, item in enumerate(references, start=1)
            ],
            "input_tokens": scenario_input,
            "output_tokens": scenario_output,
            "estimated_cost_usd": token_cost_usd(scenario_input, scenario_output),
            "version_resolution": resolver_data,
            "elapsed_seconds": time.perf_counter() - started,
            "error": error or None,
        }
        records.append(record)
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(
            f"{row['question_id']}: label={classification_ok} "
            f"content={content_ok} support={support_ok} error={error or 'none'}"
        )
        if error and _provider_error(error):
            stop_reason = "PROVIDER_ERROR_FAIL_FAST"
            break

    if logical_calls > MAX_LOGICAL_EXTERNAL_CALLS:
        raise RuntimeError("logical external call上限を超えました")
    completed = [row for row in records if not row["error"]]
    summary = {
        "scenario_count": len(SELECTED_IDS),
        "completed_count": len(completed),
        "logical_external_calls": logical_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": args.max_cost_usd,
        "target_composite_ok": any(
            row["question_id"] == TARGET_ID and row["composite_ok"] for row in completed
        ),
        "control_composite_correct": sum(
            row["composite_ok"] for row in completed if row["role"] == "control"
        ),
        "control_count": len(CONTROL_IDS),
        "gate_passed": (
            stop_reason == "COMPLETED"
            and len(completed) == len(SELECTED_IDS)
            and all(row["composite_ok"] for row in completed)
        ),
        "stop_reason": stop_reason,
        "sealed_holdout_accessed": False,
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
