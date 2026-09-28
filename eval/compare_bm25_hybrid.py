"""Compare contextual dense retrieval with Sudachi BM25 plus RRF on 100 questions."""

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

from config import BASE_DIR, DOCS_DIR, TOP_K
from eval.analyze_retrieval_failures import analyze_records
from eval.bm25_hybrid_retriever import (
    BM25_B,
    BM25_K1,
    DENSE_CANDIDATE_K,
    RRF_K,
    SPARSE_CANDIDATE_K,
    BM25Index,
    create_sudachi_tokenizer,
    reciprocal_rank_fusion,
)
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.compare_embedding_models import (
    load_elements,
    load_or_create_vectors,
    percentile_95,
    retrieval_mrr,
)
from eval.compare_retrieval import compare_results, load_results
from eval.compare_vector_backends import filter_questions
from eval.embedding_profiles import PROFILES
from eval.evaluate_retrieval import (
    evaluate_retrieval,
    load_evaluation_questions,
    save_results,
)
from src.embedding_representation import contextual_heading_document_text
from src.qdrant_index import QdrantVectorIndex


DEFAULT_BASELINE = BASE_DIR / "eval/results/large_formal_contextual_heading.csv"
DEFAULT_DOCUMENT_CACHE = (
    BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
)
DEFAULT_QUERY_CACHE = BASE_DIR / ".eval_cache/large_formal_query_vectors.json"
DEFAULT_INPUT = BASE_DIR / "eval/evaluation_questions_500.csv"
TARGET_IDS = {"Q156", "Q291", "Q436"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _headings(hits: list) -> list[str]:
    return [
        " > ".join(
            str(hit.element.metadata[key])
            for key in ("見出し1", "見出し2", "見出し3")
            if hit.element.metadata.get(key)
        )
        for hit in hits
    ]


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


def _verify_reproduced_baseline(reproduced: list[dict], committed_path: Path) -> None:
    committed = load_results(committed_path)
    current = {row["question_id"]: row for row in reproduced}
    if set(committed) != set(current):
        raise ValueError("再現baselineと保存baselineの質問集合が一致しません")
    for question_id in committed:
        for field in (
            "retrieved_document_ids",
            "retrieved_headings",
            "hit_at_5",
            "evidence_hit_at_5",
        ):
            if str(committed[question_id][field]) != str(current[question_id][field]):
                raise ValueError(
                    f"再現baselineが保存結果と一致しません: {question_id} / {field}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")

    questions = filter_questions(load_evaluation_questions(args.input), "formal")
    if len(questions) != 100 or not TARGET_IDS <= {
        row["question_id"] for row in questions
    }:
        raise ValueError("固定したformal 100問またはtarget 3問がありません")
    elements = load_elements(DOCS_DIR)
    texts = [contextual_heading_document_text(element) for element in elements]
    profile = PROFILES["gemini-embedding-001"]
    document_ids = [
        f"{element.id}:{hashlib.sha256(text.encode()).hexdigest()}"
        for element, text in zip(elements, texts, strict=True)
    ]

    def cache_miss(_texts: list[str]) -> list[list[float]]:
        raise ValueError("Embedding cache missです。外部APIを暗黙に呼びません")

    vectors, cache_hit, _ = load_or_create_vectors(
        args.document_cache,
        profile=profile,
        kind="contextual-heading-document-v1",
        ids=document_ids,
        texts=texts,
        embed=cache_miss,
    )
    if not cache_hit:
        raise AssertionError("document cacheを再利用できませんでした")
    query_vectors = load_baseline_query_vectors(args.query_cache, questions)
    dense_index = QdrantVectorIndex(
        client=QdrantClient(":memory:"), collection_name="bm25-hybrid-dense-baseline"
    )
    dense_index.ensure_collection(profile.dimensions)
    dense_index.upsert(
        elements, vectors, "gemini:gemini-embedding-001:contextual-heading"
    )
    bm25 = BM25Index(elements, tokenize=create_sudachi_tokenizer())

    dense_latencies = []
    hybrid_latencies = []
    sparse_rank_diagnostics: dict[str, list[dict[str, Any]]] = {}

    def retrieve_dense(query: str, top_k: int):
        started = time.perf_counter()
        hits = dense_index.search(query_vectors[query], limit=top_k)
        dense_latencies.append(time.perf_counter() - started)
        return _as_retrieval_results(hits)

    def retrieve_hybrid(query: str, top_k: int):
        started = time.perf_counter()
        dense_hits = dense_index.search(query_vectors[query], limit=DENSE_CANDIDATE_K)
        sparse_hits = bm25.search(query, limit=SPARSE_CANDIDATE_K)
        fused = reciprocal_rank_fusion(
            dense_hits, sparse_hits, limit=top_k, rrf_k=RRF_K
        )
        hybrid_latencies.append(time.perf_counter() - started)
        question_id = next(
            row["question_id"] for row in questions if row["question"] == query
        )
        if question_id in TARGET_IDS:
            sparse_rank_diagnostics[question_id] = [
                {
                    "rank": hit.rank,
                    "document_id": hit.element.metadata.get("document_id", ""),
                    "heading": heading,
                    "element_id": str(hit.element.id),
                    "score": hit.score,
                }
                for hit, heading in zip(
                    sparse_hits, _headings(sparse_hits), strict=True
                )
            ]
        return _as_retrieval_results(fused)

    with redirect_stdout(StringIO()):
        reproduced_baseline = evaluate_retrieval(questions, retrieve_fn=retrieve_dense)
        candidate = evaluate_retrieval(questions, retrieve_fn=retrieve_hybrid)
    _verify_reproduced_baseline(reproduced_baseline, args.baseline)

    args.output_dir.mkdir(parents=True)
    candidate_path = args.output_dir / "candidate.csv"
    save_results(candidate, candidate_path)
    summary, changes = compare_results(
        load_results(args.baseline), load_results(candidate_path)
    )
    baseline = load_results(args.baseline)
    candidate_by_id = load_results(candidate_path)
    improved_targets = sorted(
        question_id
        for question_id in TARGET_IDS
        if baseline[question_id]["evidence_hit_at_5"] == "0"
        and candidate_by_id[question_id]["evidence_hit_at_5"] == "1"
    )
    evidence_regressions = sorted(
        question_id
        for question_id in baseline
        if baseline[question_id]["evidence_hit_at_5"] == "1"
        and candidate_by_id[question_id]["evidence_hit_at_5"] == "0"
    )
    document_regressions = sorted(
        question_id
        for question_id in baseline
        if baseline[question_id]["hit_at_5"] == "1"
        and candidate_by_id[question_id]["hit_at_5"] == "0"
    )
    gate_passed = (
        len(improved_targets) >= 2
        and not evidence_regressions
        and not document_regressions
    )
    manifest = {
        "artifact_version": "bm25-hybrid-comparison-v1",
        "input": str(args.input),
        "baseline": str(args.baseline),
        "candidate": str(candidate_path),
        "source_sha256": {
            "input": _sha256(args.input),
            "baseline": _sha256(args.baseline),
            "document_cache": _sha256(args.document_cache),
            "query_cache": _sha256(args.query_cache),
        },
        "questions": len(questions),
        "retrieval_applicable_questions": sum(
            bool(row["retrieval_applicable"]) for row in candidate
        ),
        "elements": len(elements),
        "embedding": "gemini-embedding-001 contextual-heading-v1 (cache reused)",
        "bm25": {
            "tokenizer": "SudachiPy SplitMode.C normalized_form",
            "k1": BM25_K1,
            "b": BM25_B,
            "document_representation": "contextual_heading_document_text",
        },
        "fusion": {
            "method": "RRF",
            "rrf_k": RRF_K,
            "dense_candidate_k": DENSE_CANDIDATE_K,
            "sparse_candidate_k": SPARSE_CANDIDATE_K,
            "output_top_k": TOP_K,
        },
        "external_api_calls": 0,
        "estimated_external_cost_usd": 0.0,
        "sealed_holdout_accessed": False,
        "baseline_reproduced_exactly": True,
        "summary": summary,
        "changed_questions": changes,
        "failure_analysis": {
            f"at_{k}": analyze_records(candidate, k)[0] for k in (3, 5)
        },
        "target_ids": sorted(TARGET_IDS),
        "improved_target_ids": improved_targets,
        "evidence_hit_at_5_regressions": evidence_regressions,
        "document_hit_at_5_regressions": document_regressions,
        "gate_passed": gate_passed,
        "decision": "RUN_ANSWER_REGRESSION" if gate_passed else "DO_NOT_ADOPT",
        "retrieval_mrr_first_evidence": retrieval_mrr(candidate),
        "timing_seconds": {
            "dense_search_p50": statistics.median(dense_latencies),
            "dense_search_p95": percentile_95(dense_latencies),
            "hybrid_search_p50": statistics.median(hybrid_latencies),
            "hybrid_search_p95": percentile_95(hybrid_latencies),
        },
        "target_sparse_top_20": sparse_rank_diagnostics,
    }
    _write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
