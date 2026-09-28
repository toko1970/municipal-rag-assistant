"""Compare dense retrieval with deterministic multi-intent query decomposition."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from config import BASE_DIR, DOCS_DIR, GOOGLE_API_KEY
from eval.analyze_retrieval_failures import analyze_records
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.compare_embedding_models import (
    load_elements,
    load_or_create_vectors,
    percentile_95,
    retrieval_mrr,
)
from eval.compare_retrieval import compare_results, load_results
from eval.compare_vector_backends import filter_questions
from eval.embedding_profiles import PROFILES, GeminiOneEmbedder
from eval.evaluate_retrieval import (
    evaluate_retrieval,
    load_evaluation_questions,
    save_results,
)
from eval.query_decomposition import decompose_query, retrieve_decomposed
from src.embedding_representation import contextual_heading_document_text
from src.qdrant_index import QdrantVectorIndex


DEFAULT_DOCUMENT_CACHE = (
    BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
)
DEFAULT_QUERY_CACHE = BASE_DIR / ".eval_cache/large_formal_query_vectors.json"
DEFAULT_SUBQUERY_CACHE = (
    BASE_DIR / ".eval_cache/query_decomposition_gemini_001_queries.json"
)
DEFAULT_INPUT = BASE_DIR / "eval/evaluation_questions_500.csv"
TARGET_IDS = {"Q156", "Q291", "Q436"}
MAX_LOGICAL_EXTERNAL_CALLS = 1
MAX_COST_USD = 0.001
# Conservative ceiling based on the current Gemini Embedding 2 standard text price.
EMBEDDING_PRICE_USD_PER_MILLION_TOKENS = 0.20


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _as_retrieval_results(hits: list) -> list[tuple[Any, float]]:
    results = []
    for hit in hits:
        metadata = {
            **hit.element.metadata,
            "document_id": hit.element.metadata.get("document_id", ""),
        }
        document = type(
            "EvaluationDocument",
            (),
            {"metadata": metadata, "page_content": hit.element.content},
        )()
        results.append((document, hit.score))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--subquery-cache", type=Path, default=DEFAULT_SUBQUERY_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")

    questions = filter_questions(load_evaluation_questions(args.input), "formal")
    if len(questions) != 100 or not TARGET_IDS <= {
        row["question_id"] for row in questions
    }:
        raise ValueError("固定したformal 100問またはtarget 3問がありません")

    decomposition_by_question = {
        row["question"]: decompose_query(row["question"]) for row in questions
    }
    decomposed_rows = [
        row
        for row in questions
        if decomposition_by_question[row["question"]] != [row["question"]]
    ]
    subqueries = list(
        dict.fromkeys(
            subquery
            for row in decomposed_rows
            for subquery in decomposition_by_question[row["question"]]
        )
    )
    if not subqueries:
        raise ValueError("分解対象の質問がありません")

    # One Japanese character per token is deliberately conservative for the cap.
    estimated_tokens_upper_bound = sum(len(query) for query in subqueries)
    estimated_cost_upper_bound = (
        estimated_tokens_upper_bound
        * EMBEDDING_PRICE_USD_PER_MILLION_TOKENS
        / 1_000_000
    )
    if estimated_cost_upper_bound > MAX_COST_USD:
        raise ValueError("埋め込み費用の事前上限を超えます")

    elements = load_elements(DOCS_DIR)
    texts = [contextual_heading_document_text(element) for element in elements]
    profile = PROFILES["gemini-embedding-001"]
    document_ids = [
        f"{element.id}:{hashlib.sha256(text.encode()).hexdigest()}"
        for element, text in zip(elements, texts, strict=True)
    ]

    def cache_miss(_texts: list[str]) -> list[list[float]]:
        raise ValueError("Embedding cache missです。外部APIを暗黙に呼びません")

    document_vectors, document_cache_hit, _ = load_or_create_vectors(
        args.document_cache,
        profile=profile,
        kind="contextual-heading-document-v1",
        ids=document_ids,
        texts=texts,
        embed=cache_miss,
    )
    if not document_cache_hit:
        raise AssertionError("document cacheを再利用できませんでした")
    original_vectors = load_baseline_query_vectors(args.query_cache, questions)

    embedder = GeminiOneEmbedder(profile, GOOGLE_API_KEY)
    subquery_ids = [
        f"query:{hashlib.sha256(query.encode()).hexdigest()}" for query in subqueries
    ]
    subquery_vectors, subquery_cache_hit, embedding_seconds = load_or_create_vectors(
        args.subquery_cache,
        profile=profile,
        kind="query-decomposition-v1",
        ids=subquery_ids,
        texts=subqueries,
        embed=embedder.embed_queries,
    )
    if embedder.request_count > MAX_LOGICAL_EXTERNAL_CALLS:
        raise RuntimeError("外部API呼び出し上限を超えました")
    vectors_by_query = {
        **original_vectors,
        **dict(zip(subqueries, subquery_vectors, strict=True)),
    }

    dense_index = QdrantVectorIndex(
        client=QdrantClient(":memory:"),
        collection_name="query-decomposition-dense-comparison",
    )
    dense_index.ensure_collection(profile.dimensions)
    dense_index.upsert(
        elements, vectors=document_vectors, embedding_profile="gemini-001-contextual"
    )

    baseline_latencies: list[float] = []
    candidate_latencies: list[float] = []

    def search(query: str, limit: int):
        return dense_index.search(vectors_by_query[query], limit=limit)

    def retrieve_baseline(query: str, top_k: int):
        started = time.perf_counter()
        hits = search(query, top_k)
        baseline_latencies.append(time.perf_counter() - started)
        return _as_retrieval_results(hits)

    def retrieve_candidate(query: str, top_k: int):
        started = time.perf_counter()
        hits = retrieve_decomposed(query, top_k=top_k, search=search)
        candidate_latencies.append(time.perf_counter() - started)
        return _as_retrieval_results(hits)

    with redirect_stdout(StringIO()):
        baseline_records = evaluate_retrieval(questions, retrieve_fn=retrieve_baseline)
        candidate_records = evaluate_retrieval(
            questions, retrieve_fn=retrieve_candidate
        )

    args.output_dir.mkdir(parents=True)
    baseline_path = args.output_dir / "baseline.csv"
    candidate_path = args.output_dir / "candidate.csv"
    save_results(baseline_records, baseline_path)
    save_results(candidate_records, candidate_path)
    baseline = load_results(baseline_path)
    candidate = load_results(candidate_path)
    summary, changes = compare_results(baseline, candidate)

    improved_targets = sorted(
        question_id
        for question_id in TARGET_IDS
        if baseline[question_id]["evidence_hit_at_5"] == "0"
        and candidate[question_id]["evidence_hit_at_5"] == "1"
    )
    evidence_regressions = sorted(
        question_id
        for question_id in baseline
        if baseline[question_id]["evidence_hit_at_5"] == "1"
        and candidate[question_id]["evidence_hit_at_5"] == "0"
    )
    document_regressions = sorted(
        question_id
        for question_id in baseline
        if baseline[question_id]["hit_at_5"] == "1"
        and candidate[question_id]["hit_at_5"] == "0"
    )
    gate_passed = (
        len(improved_targets) >= 2
        and not evidence_regressions
        and not document_regressions
    )
    manifest = {
        "artifact_version": "query-decomposition-comparison-v1",
        "input": str(args.input),
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "source_sha256": {
            "input": _sha256(args.input),
            "document_cache": _sha256(args.document_cache),
            "query_cache": _sha256(args.query_cache),
            "subquery_cache": _sha256(args.subquery_cache),
        },
        "questions": len(questions),
        "retrieval_applicable_questions": sum(
            bool(row["retrieval_applicable"]) for row in candidate_records
        ),
        "elements": len(elements),
        "embedding": "gemini-embedding-001 contextual-heading-v1",
        "decomposition": {
            "method": "deterministic domain-event and requested-facet rules",
            "decomposed_question_ids": [row["question_id"] for row in decomposed_rows],
            "unique_subqueries": len(subqueries),
            "queries_by_question_id": {
                row["question_id"]: decomposition_by_question[row["question"]]
                for row in decomposed_rows
            },
            "uses_gold_fields": False,
            "merge": "equal per-intent quota, deduplicate, fill from original query",
        },
        "external_api": {
            "logical_calls": embedder.request_count,
            "max_logical_calls": MAX_LOGICAL_EXTERNAL_CALLS,
            "retry": 0,
            "subquery_cache_hit": subquery_cache_hit,
            "estimated_tokens_upper_bound": estimated_tokens_upper_bound,
            "estimated_cost_upper_bound_usd": estimated_cost_upper_bound,
            "max_cost_usd": MAX_COST_USD,
        },
        "sealed_holdout_accessed": False,
        "comparison_condition": "baseline and candidate generated in the same run",
        "summary": summary,
        "changed_questions": changes,
        "failure_analysis": {
            f"at_{k}": analyze_records(candidate_records, k)[0] for k in (3, 5)
        },
        "target_ids": sorted(TARGET_IDS),
        "improved_target_ids": improved_targets,
        "evidence_hit_at_5_regressions": evidence_regressions,
        "document_hit_at_5_regressions": document_regressions,
        "gate_passed": gate_passed,
        "decision": "RUN_ANSWER_REGRESSION" if gate_passed else "DO_NOT_ADOPT",
        "retrieval_mrr_first_evidence": retrieval_mrr(candidate_records),
        "timing_seconds": {
            "subquery_embedding": embedding_seconds,
            "baseline_search_p50": statistics.median(baseline_latencies),
            "baseline_search_p95": percentile_95(baseline_latencies),
            "candidate_search_p50": statistics.median(candidate_latencies),
            "candidate_search_p95": percentile_95(candidate_latencies),
        },
    }
    _write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
