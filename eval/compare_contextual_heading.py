"""Evaluate heading-enriched document embeddings in an isolated Qdrant collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from config import CHUNK_OVERLAP, CHUNK_SIZE, DOCS_DIR, EMBEDDING_MODEL_NAME, TOP_K
from eval.analyze_retrieval_failures import analyze_records
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
from eval.qdrant_retriever import retrieve_by_vector
from src.embedding_representation import contextual_heading_document_text
from src.embeddings import get_embeddings
from src.qdrant_index import QdrantVectorIndex


COLLECTION_NAME = "municipal_docs_eval_gemini_001_contextual_heading_v1"
def load_baseline_query_vectors(
    path: Path, questions: list[dict]
) -> dict[str, list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    question_texts = [row["question"] for row in questions]
    if payload.get("embedding_model") != EMBEDDING_MODEL_NAME:
        raise ValueError("baseline query cacheのEmbeddingモデルが一致しません")
    cached_questions = payload.get("questions", [])
    vectors = payload.get("vectors", [])
    if len(vectors) != len(cached_questions):
        raise ValueError("baseline query cacheのvector数が一致しません")
    if len(set(cached_questions)) != len(cached_questions):
        raise ValueError("baseline query cacheに重複した質問があります")
    cached_vectors = dict(zip(cached_questions, vectors, strict=True))
    missing = [question for question in question_texts if question not in cached_vectors]
    if missing:
        raise ValueError("baseline query cacheに評価対象の質問がありません")
    return {question: cached_vectors[question] for question in question_texts}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--variant-type", default="formal")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--query-cache", type=Path, required=True)
    parser.add_argument("--document-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()

    questions = filter_questions(
        load_evaluation_questions(args.input), args.variant_type
    )
    elements = load_elements(DOCS_DIR)
    contextual_texts = [
        contextual_heading_document_text(element) for element in elements
    ]
    profile = PROFILES["gemini-embedding-001"]
    embeddings = get_embeddings()
    document_ids = [
        f"{element.id}:{hashlib.sha256(text.encode()).hexdigest()}"
        for element, text in zip(elements, contextual_texts, strict=True)
    ]
    request_count = 0

    def embed_documents(texts: list[str]) -> list[list[float]]:
        nonlocal request_count
        request_count += 1
        return embeddings.embed_documents(
            texts,
            batch_size=100,
            task_type="RETRIEVAL_DOCUMENT",
        )

    document_vectors, document_cache_hit, embedding_seconds = (
        load_or_create_vectors(
            args.document_cache,
            profile=profile,
            kind="contextual-heading-document-v1",
            ids=document_ids,
            texts=contextual_texts,
            embed=embed_documents,
        )
    )
    query_vectors = load_baseline_query_vectors(args.query_cache, questions)
    if any(len(vector) != profile.dimensions for vector in query_vectors.values()):
        raise ValueError("baseline query vectorの次元がprofileと一致しません")

    index = QdrantVectorIndex(collection_name=COLLECTION_NAME)
    indexing_started = time.perf_counter()
    index.ensure_collection(profile.dimensions)
    index.upsert(elements, document_vectors, "gemini-embedding-001:contextual-heading-v1")
    indexing_seconds = time.perf_counter() - indexing_started
    expected_ids = {element.id for element in elements}
    actual_ids = index.list_point_ids()
    if actual_ids != expected_ids:
        raise ValueError(
            "実験collectionのpoint IDが入力要素と一致しません: "
            f"missing={len(expected_ids - actual_ids)}, unexpected={len(actual_ids - expected_ids)}"
        )

    search_latencies = []

    def retrieve(query: str, top_k: int):
        started = time.perf_counter()
        result = retrieve_by_vector(query_vectors[query], top_k, index=index)
        search_latencies.append(time.perf_counter() - started)
        return result

    with redirect_stdout(StringIO()):
        records = evaluate_retrieval(questions, retrieve_fn=retrieve)
    save_results(records, args.output)
    summary, changes = compare_results(
        load_results(args.baseline), load_results(args.output)
    )
    manifest = {
        "experiment": "contextual-heading-v1",
        "input": str(args.input),
        "input_sha256": file_sha256(args.input),
        "variant_type": args.variant_type,
        "questions": len(questions),
        "elements": len(elements),
        "embedding_model": EMBEDDING_MODEL_NAME,
        "dimensions": profile.dimensions,
        "collection_name": COLLECTION_NAME,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "top_k": TOP_K,
        "document_representation": (
            "文書: {document_name}\\n見出し: {heading_path}\\n\\n{original_content}"
        ),
        "query_representation": "baseline RETRIEVAL_QUERY vectorを再利用",
        "document_cache_hit": document_cache_hit,
        "embedding_provider_calls": request_count,
        "timing_seconds": {
            "document_embedding": embedding_seconds,
            "qdrant_indexing": indexing_seconds,
            "search_p50": statistics.median(search_latencies),
            "search_p95": percentile_95(search_latencies),
        },
        "retrieval_mrr_first_evidence": retrieval_mrr(records),
        "baseline": str(args.baseline),
        "summary": summary,
        "changed_questions": changes,
        "failure_analysis": {
            f"at_{k}": analyze_records(records, k)[0] for k in (1, 3, 5)
        },
        "output": str(args.output),
    }
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
