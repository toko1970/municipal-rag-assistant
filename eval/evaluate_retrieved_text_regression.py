"""Run a bounded text regression through the current structured RAG pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME, TOP_K
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.compare_embedding_models import load_elements, load_or_create_vectors
from eval.embedding_profiles import PROFILES
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_models import load_questions
from eval.evaluate_visual_answers import token_cost_usd
from src.embedding_representation import contextual_heading_document_text
from src.llm_provider import GeminiProvider
from src.qdrant_index import QdrantVectorIndex
from src.query_service import (
    CLASSIFICATION_DECISION_VERSION,
    CLASSIFICATION_PROMPT_VERSION,
    GENERATION_PROMPT_VERSION,
    answer_question,
    load_schema,
)


ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
DEFAULT_DOCUMENT_CACHE = (
    BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
)
DEFAULT_QUERY_CACHE = BASE_DIR / ".eval_cache/large_formal_query_vectors.json"
RESERVE_USD_PER_SCENARIO = 0.003


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prepare_text_corpus(document_cache: Path) -> QdrantVectorIndex:
    elements = load_elements(BASE_DIR / "docs")
    texts = [contextual_heading_document_text(element) for element in elements]
    ids = [
        f"{element.id}:{hashlib.sha256(text.encode()).hexdigest()}"
        for element, text in zip(elements, texts, strict=True)
    ]
    profile = PROFILES["gemini-embedding-001"]

    def cache_miss(_texts: list[str]) -> list[list[float]]:
        raise ValueError("document vector cacheがありません。APIで暗黙生成しません")

    vectors, cache_hit, _ = load_or_create_vectors(
        document_cache,
        profile=profile,
        kind="contextual-heading-document-v1",
        ids=ids,
        texts=texts,
        embed=cache_miss,
    )
    if not cache_hit:
        raise AssertionError("document vector cacheを使用できませんでした")
    client = QdrantClient(":memory:")
    index = QdrantVectorIndex(client=client, collection_name="text-regression-v1")
    index.ensure_collection(profile.dimensions)
    index.upsert(elements, vectors, "gemini:gemini-embedding-001:contextual-heading")
    return index


def _expected_evidence(row: dict[str, str]) -> set[str]:
    return {
        item.strip()
        for item in str(row.get("expected_evidence", "")).split("|")
        if item.strip()
    }


def _retrieval_outcome(row: dict[str, str], logger: EvaluationLogger) -> dict[str, Any]:
    retrieved = []
    for hit in logger.retrieval_hits:
        document_id = str(hit.element.metadata.get("document_id", ""))
        heading_parts = [
            str(hit.element.metadata[key])
            for key in ("見出し1", "見出し2", "見出し3")
            if hit.element.metadata.get(key)
        ]
        full_heading = (
            " > ".join(heading_parts)
            if heading_parts
            else str(hit.element.metadata.get("heading_path", hit.element.heading))
        )
        retrieved.append(
            {
                "rank": hit.rank,
                "document_id": document_id,
                "heading": full_heading,
                "element_id": str(hit.element.id),
            }
        )
    expected = _expected_evidence(row)
    actual = {f"{item['document_id']}::{item['heading']}" for item in retrieved}
    applicable = bool(expected)
    return {
        "retrieval_applicable": applicable,
        "retrieval_ok": (expected <= actual) if applicable else None,
        "expected_evidence": sorted(expected),
        "retrieved": retrieved,
    }


def _is_provider_error(error: str) -> bool:
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


def run_regression(
    *,
    questions: list[dict[str, str]],
    query_vectors: dict[str, list[float]],
    index: QdrantVectorIndex,
    output_dir: Path,
    max_cost_usd: float,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {output_dir}")
    output_dir.mkdir(parents=True)
    records_path = output_dir / "records.jsonl"
    generator = GeminiProvider(LLM_MODEL_NAME)
    classifier = GeminiProvider(CLASSIFIER_MODEL_NAME)
    input_tokens = 0
    output_tokens = 0
    records: list[dict[str, Any]] = []
    stop_reason = "COMPLETED"

    for row in questions:
        if (
            token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_SCENARIO
            > max_cost_usd
        ):
            stop_reason = "COST_LIMIT_REACHED"
            break
        logger = EvaluationLogger()
        started = time.perf_counter()
        try:
            result = answer_question(
                row["question"],
                embed_query=lambda question: query_vectors[question],
                vector_index=index,
                generator=generator,
                classifier=classifier,
                event_logger=logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                top_k=TOP_K,
            )
            error = None
        except Exception as exception:
            result = None
            error = f"{type(exception).__name__}: {exception}"

        generation_input = int(logger.generation.get("input_tokens", 0))
        generation_output = int(logger.generation.get("output_tokens", 0))
        classification_input = int(logger.classification.get("input_tokens", 0))
        classification_output = int(logger.classification.get("output_tokens", 0))
        scenario_input = generation_input + classification_input
        scenario_output = generation_output + classification_output
        input_tokens += scenario_input
        output_tokens += scenario_output
        retrieval = _retrieval_outcome(row, logger)
        generated_data = logger.generation.get("response_data") or {}
        record = {
            "question_id": row["question_id"],
            "question": row["question"],
            "difficulty": row["difficulty"],
            "expected_label": row["expected_answer_type"],
            "expected_answer_key": row["expected_answer_key"],
            **retrieval,
            "predicted_label": (
                result.get("answer_label")
                if result
                else logger.classification.get("derived_label")
            ),
            "classification_ok": bool(result)
            and result.get("answer_label") == row["expected_answer_type"],
            "classification_factors": logger.classification.get("factors"),
            "answer": result.get("answer", "") if result else "",
            "claims": (
                result.get("claims", []) if result else generated_data.get("claims", [])
            ),
            "missing_conditions": generated_data.get("missing_conditions", []),
            "content_review_status": "pending" if result else "blocked_by_error",
            "input_tokens": scenario_input,
            "output_tokens": scenario_output,
            "cost_usd": token_cost_usd(scenario_input, scenario_output),
            "elapsed_seconds": time.perf_counter() - started,
            "error": error,
        }
        records.append(record)
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        print(
            f"{row['question_id']}: retrieval={record['retrieval_ok']}, "
            f"classification={record['classification_ok']}, error={error or 'none'}"
        )
        if error and _is_provider_error(error):
            stop_reason = "PROVIDER_ERROR_FAIL_FAST"
            break

    completed = [record for record in records if record["error"] is None]
    summary = {
        "scenario_count": len(questions),
        "completed_count": len(completed),
        "error_count": len(records) - len(completed),
        "retrieval_applicable_count": sum(
            record["retrieval_applicable"] for record in completed
        ),
        "retrieval_correct": sum(
            record["retrieval_ok"] is True for record in completed
        ),
        "retrieval_not_applicable": sum(
            record["retrieval_ok"] is None for record in completed
        ),
        "classification_correct": sum(
            record["classification_ok"] for record in completed
        ),
        "content_review_pending": len(completed),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": max_cost_usd,
        "stop_reason": stop_reason,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()

    questions = load_questions(args.input, "formal")
    query_vectors = load_baseline_query_vectors(args.query_cache, questions)
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {output_dir}")
    output_dir.mkdir(parents=True)
    manifest = {
        "candidate_commit": "e24d7d4",
        "dataset_path": str(args.input),
        "dataset_sha256": _sha256(args.input),
        "query_cache_sha256": _sha256(args.query_cache),
        "document_cache_sha256": _sha256(args.document_cache),
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "generation_prompt_version": GENERATION_PROMPT_VERSION,
        "classification_prompt_version": CLASSIFICATION_PROMPT_VERSION,
        "classification_decision_version": CLASSIFICATION_DECISION_VERSION,
        "top_k": TOP_K,
        "scenario_count": len(questions),
        "max_logical_external_calls": len(questions) * 2,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "reserve_usd_per_scenario": RESERVE_USD_PER_SCENARIO,
        "evaluation_mode": "retrieved_evidence",
        "sealed_holdout_accessed": False,
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    index = prepare_text_corpus(args.document_cache)
    summary = run_regression(
        questions=questions,
        query_vectors=query_vectors,
        index=index,
        output_dir=output_dir / "evaluation",
        max_cost_usd=args.max_cost_usd,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
