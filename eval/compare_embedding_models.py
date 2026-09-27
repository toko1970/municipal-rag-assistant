"""Build an isolated Qdrant collection and evaluate one embedding profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from config import CHUNK_OVERLAP, CHUNK_SIZE, DOCS_DIR, GOOGLE_API_KEY, TOP_K
from eval.analyze_retrieval_failures import analyze_records
from eval.compare_retrieval import compare_results, load_results
from eval.compare_vector_backends import filter_questions
from eval.embedding_profiles import PROFILES, EmbeddingProfile, create_embedder
from eval.evaluate_retrieval import (
    evaluate_retrieval,
    load_evaluation_questions,
    save_results,
)
from eval.qdrant_retriever import retrieve_by_vector
from src.ingestion import build_markdown_elements
from src.qdrant_index import QdrantVectorIndex


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_elements(docs_dir: Path):
    elements = []
    for path in sorted(docs_dir.glob("*.md")):
        elements.extend(build_markdown_elements(path))
    if not elements:
        raise ValueError(f"取込対象のMarkdownがありません: {docs_dir}")
    return elements


def _cache_key(profile: EmbeddingProfile, kind: str, ids: list[str]) -> dict:
    return {"profile": profile.manifest(), "kind": kind, "ids": ids}


def load_or_create_vectors(
    path: Path,
    *,
    profile: EmbeddingProfile,
    kind: str,
    ids: list[str],
    texts: list[str],
    embed,
) -> tuple[list[list[float]], bool, float | None]:
    expected = _cache_key(profile, kind, ids)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("conditions") != expected:
            raise ValueError(f"Embedding cacheの条件が一致しません: {path}")
        return payload["vectors"], True, None

    started = time.perf_counter()
    vectors = embed(texts)
    elapsed = time.perf_counter() - started
    if len(vectors) != len(texts):
        raise ValueError(f"入力数とEmbedding数が一致しません: {len(texts)} != {len(vectors)}")
    if any(len(vector) != profile.dimensions for vector in vectors):
        dimensions = sorted({len(vector) for vector in vectors})
        raise ValueError(
            f"Embedding次元がprofileと一致しません: expected={profile.dimensions}, actual={dimensions}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"conditions": expected, "vectors": vectors}, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)
    return vectors, False, elapsed


def retrieval_mrr(records: list[dict]) -> float:
    reciprocal_ranks = []
    for record in records:
        if not record.get("expected_evidence"):
            continue
        expected = set(str(record["expected_evidence"]).split("|"))
        retrieved = [
            f"{document_id}::{heading}"
            for document_id, heading in zip(
                str(record["retrieved_document_ids"]).split("|"),
                str(record["retrieved_headings"]).split("|"),
                strict=True,
            )
        ]
        rank = next(
            (index for index, evidence in enumerate(retrieved, start=1) if evidence in expected),
            None,
        )
        reciprocal_ranks.append(0.0 if rank is None else 1 / rank)
    return statistics.fmean(reciprocal_ranks) if reciprocal_ranks else 0.0


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int(0.95 * len(ordered) + 0.999999) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--variant-type", default="formal")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path(".eval_cache"))
    parser.add_argument("--device")
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    embedder = create_embedder(profile, api_key=GOOGLE_API_KEY, device=args.device)
    questions = filter_questions(
        load_evaluation_questions(args.input), args.variant_type
    )
    elements = load_elements(DOCS_DIR)

    document_ids = [
        f"{element.id}:{hashlib.sha256(element.content.encode()).hexdigest()}"
        for element in elements
    ]
    question_ids = [
        f"{row['question_id']}:{hashlib.sha256(row['question'].encode()).hexdigest()}"
        for row in questions
    ]
    document_vectors, document_cache_hit, document_seconds = load_or_create_vectors(
        args.cache_dir / f"{profile.key}-documents.json",
        profile=profile,
        kind="document",
        ids=document_ids,
        texts=[element.content for element in elements],
        embed=embedder.embed_documents,
    )
    query_vectors, query_cache_hit, query_seconds = load_or_create_vectors(
        args.cache_dir / f"{profile.key}-formal-queries.json",
        profile=profile,
        kind="query",
        ids=question_ids,
        texts=[row["question"] for row in questions],
        embed=embedder.embed_queries,
    )

    index = QdrantVectorIndex(collection_name=profile.collection_name)
    indexing_started = time.perf_counter()
    index.ensure_collection(profile.dimensions)
    index.upsert(elements, document_vectors, profile.key)
    indexing_seconds = time.perf_counter() - indexing_started
    actual_ids = index.list_point_ids()
    expected_ids = {element.id for element in elements}
    if actual_ids != expected_ids:
        raise ValueError(
            "実験collectionのpoint IDが入力要素と一致しません: "
            f"missing={len(expected_ids - actual_ids)}, unexpected={len(actual_ids - expected_ids)}"
        )

    vectors_by_question = dict(
        zip((row["question"] for row in questions), query_vectors, strict=True)
    )
    search_latencies = []

    def retrieve(query: str, top_k: int):
        started = time.perf_counter()
        result = retrieve_by_vector(vectors_by_question[query], top_k, index=index)
        search_latencies.append(time.perf_counter() - started)
        return result

    with redirect_stdout(StringIO()):
        records = evaluate_retrieval(questions, retrieve_fn=retrieve)
    save_results(records, args.output)

    baseline = load_results(args.baseline)
    candidate = load_results(args.output)
    summary, changes = compare_results(baseline, candidate)
    failure_analysis = {
        f"at_{k}": analyze_records(records, k)[0] for k in (1, 3, 5)
    }
    manifest = {
        "profile": profile.manifest(),
        "input": str(args.input),
        "input_sha256": file_sha256(args.input),
        "variant_type": args.variant_type,
        "questions": len(questions),
        "elements": len(elements),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "top_k": TOP_K,
        "document_cache_hit": document_cache_hit,
        "query_cache_hit": query_cache_hit,
        "provider_calls": embedder.request_count,
        "runtime_device": embedder.runtime_device,
        "timing_seconds": {
            "document_embedding": document_seconds,
            "query_embedding": query_seconds,
            "qdrant_indexing": indexing_seconds,
            "search_p50": statistics.median(search_latencies),
            "search_p95": percentile_95(search_latencies),
        },
        "retrieval_mrr_first_evidence": retrieval_mrr(records),
        "baseline": str(args.baseline),
        "summary": summary,
        "changed_questions": changes,
        "failure_analysis": failure_analysis,
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
