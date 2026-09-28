"""Run a bounded paired answer regression for query decomposition targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from config import (
    BASE_DIR,
    CLASSIFIER_MODEL_NAME,
    GOOGLE_API_KEY,
    LLM_MODEL_NAME,
    TOP_K,
)
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.compare_embedding_models import load_or_create_vectors
from eval.embedding_profiles import PROFILES
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_models import load_questions
from eval.evaluate_retrieved_text_regression import prepare_text_corpus
from eval.evaluate_visual_answers import token_cost_usd
from eval.query_decomposition import decompose_query, retrieve_decomposed
from src.llm_provider import GeminiProvider
from src.query_service import answer_question, load_schema


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
DEFAULT_RETRIEVAL_MANIFEST = (
    BASE_DIR / "eval/results/query_decomposition_comparison_v1/manifest.json"
)
TARGET_IDS = ("Q291", "Q436")
MAX_LOGICAL_EXTERNAL_CALLS = 12
RESERVE_USD_PER_SCENARIO = 0.005
CONTENT_PATTERNS = {
    "Q291": (r"認定月", r"15日以内"),
    "Q436": (r"(支給)?停止", r"住所変更届", r"14日以内"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _provider(model: str) -> GeminiProvider:
    client = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
        max_retries=0,
    )
    return GeminiProvider(model, client=client)


class QuestionAwareIndex:
    def __init__(self, base_index, vectors: dict[str, list[float]], *, decompose: bool):
        self.base_index = base_index
        self.vectors = vectors
        self.decompose = decompose
        self.question = ""

    def select_question(self, question: str) -> None:
        self.question = question

    def search(self, _query_vector: list[float], limit: int):
        if not self.question:
            raise RuntimeError("検索前に質問が選択されていません")
        if not self.decompose:
            return self.base_index.search(self.vectors[self.question], limit)
        return retrieve_decomposed(
            self.question,
            top_k=limit,
            search=lambda query, top_k: self.base_index.search(
                self.vectors[query], top_k
            ),
        )


def _provider_error(error: str) -> bool:
    lowered = error.lower()
    return any(
        marker in lowered
        for marker in (
            "429",
            "resource_exhausted",
            "serviceunavailable",
            "deadlineexceeded",
            "connectionerror",
            "apierror",
        )
    )


def _content_ok(question_id: str, answer: str) -> bool:
    return all(re.search(pattern, answer) for pattern in CONTENT_PATTERNS[question_id])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--subquery-cache", type=Path, default=DEFAULT_SUBQUERY_CACHE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument(
        "--retrieval-manifest", type=Path, default=DEFAULT_RETRIEVAL_MANIFEST
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_cost_usd < len(TARGET_IDS) * 2 * RESERVE_USD_PER_SCENARIO:
        raise ValueError("費用上限が4シナリオの予約額を下回っています")

    retrieval_manifest = json.loads(args.retrieval_manifest.read_text(encoding="utf-8"))
    if not retrieval_manifest.get("gate_passed"):
        raise ValueError("検索gateを通過していません")
    if set(retrieval_manifest.get("improved_target_ids", [])) != set(TARGET_IDS):
        raise ValueError("回答回帰対象が検索改善対象と一致しません")

    all_questions = load_questions(args.input, "formal")
    by_id = {row["question_id"]: row for row in all_questions}
    questions = [by_id[question_id] for question_id in TARGET_IDS]
    original_vectors = load_baseline_query_vectors(args.query_cache, questions)

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
    indexes = {
        "baseline": QuestionAwareIndex(base_index, vectors, decompose=False),
        "query_decomposition": QuestionAwareIndex(base_index, vectors, decompose=True),
    }

    args.output_dir.mkdir(parents=True)
    records_path = args.output_dir / "records.jsonl"
    manifest = {
        "experiment": "query-decomposition-answer-regression-v1",
        "dataset_sha256": _sha256(args.input),
        "retrieval_manifest_sha256": _sha256(args.retrieval_manifest),
        "query_cache_sha256": _sha256(args.query_cache),
        "subquery_cache_sha256": _sha256(args.subquery_cache),
        "document_cache_sha256": _sha256(args.document_cache),
        "target_ids": list(TARGET_IDS),
        "variants": list(indexes),
        "content_patterns": CONTENT_PATTERNS,
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "top_k": TOP_K,
        "max_logical_external_calls": MAX_LOGICAL_EXTERNAL_CALLS,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "sealed_holdout_accessed": False,
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
        for variant, index in indexes.items():
            if (
                token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_SCENARIO
                > args.max_cost_usd
            ):
                stop_reason = "COST_LIMIT_REACHED"
                break
            index.select_question(row["question"])
            logger = EvaluationLogger()
            started = time.perf_counter()
            error = ""
            result = None
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
                )
            except Exception as exception:
                error = f"{type(exception).__name__}: {exception}"

            generation_input = int(logger.generation.get("input_tokens", 0))
            generation_output = int(logger.generation.get("output_tokens", 0))
            classification_input = int(logger.classification.get("input_tokens", 0))
            classification_output = int(logger.classification.get("output_tokens", 0))
            resolver_data = result.get("version_resolution", {}) if result else {}
            resolver_input = int(resolver_data.get("input_tokens", 0))
            resolver_output = int(resolver_data.get("output_tokens", 0))
            scenario_input = generation_input + classification_input + resolver_input
            scenario_output = (
                generation_output + classification_output + resolver_output
            )
            input_tokens += scenario_input
            output_tokens += scenario_output
            logical_calls += 2 + int(resolver_data.get("status") != "NOT_REQUIRED")

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
                "variant": variant,
                "question": row["question"],
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
                f"{row['question_id']} {variant}: "
                f"label={classification_ok} content={content_ok} "
                f"support={support_ok} error={error or 'none'}"
            )
            if error and _provider_error(error):
                stop_reason = "PROVIDER_ERROR_FAIL_FAST"
                break
        if stop_reason != "COMPLETED":
            break

    if logical_calls > MAX_LOGICAL_EXTERNAL_CALLS:
        raise RuntimeError("logical external call上限を超えました")
    by_key = {(row["question_id"], row["variant"]): row for row in records}
    completed_pairs = [
        question_id
        for question_id in TARGET_IDS
        if (question_id, "baseline") in by_key
        and (question_id, "query_decomposition") in by_key
        and not by_key[(question_id, "baseline")]["error"]
        and not by_key[(question_id, "query_decomposition")]["error"]
    ]
    improvements = [
        question_id
        for question_id in completed_pairs
        if not by_key[(question_id, "baseline")]["composite_ok"]
        and by_key[(question_id, "query_decomposition")]["composite_ok"]
    ]
    regressions = [
        question_id
        for question_id in completed_pairs
        if by_key[(question_id, "baseline")]["composite_ok"]
        and not by_key[(question_id, "query_decomposition")]["composite_ok"]
    ]
    summary = {
        "scenario_count": len(TARGET_IDS) * 2,
        "completed_scenario_count": sum(not row["error"] for row in records),
        "completed_pair_ids": completed_pairs,
        "logical_external_calls": logical_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": args.max_cost_usd,
        "baseline_composite_correct": sum(
            by_key[(question_id, "baseline")]["composite_ok"]
            for question_id in completed_pairs
        ),
        "candidate_composite_correct": sum(
            by_key[(question_id, "query_decomposition")]["composite_ok"]
            for question_id in completed_pairs
        ),
        "improved_ids": improvements,
        "regressed_ids": regressions,
        "gate_passed": (
            stop_reason == "COMPLETED"
            and len(completed_pairs) == len(TARGET_IDS)
            and len(improvements) >= 1
            and not regressions
            and all(
                by_key[(question_id, "query_decomposition")]["composite_ok"]
                for question_id in TARGET_IDS
            )
        ),
        "stop_reason": stop_reason,
        "sealed_holdout_accessed": False,
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
