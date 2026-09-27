"""Compare Chroma and Qdrant using one shared query embedding per question."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Callable

from config import CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_MODEL_NAME, TOP_K
from eval.compare_retrieval import compare_results
from eval.evaluate_retrieval import (
    evaluate_retrieval,
    load_evaluation_questions,
    save_results,
)
from eval.qdrant_retriever import retrieve_by_vector
from src.embeddings import get_embeddings
from src.qdrant_index import QdrantVectorIndex
from src.retriever import get_vector_store


@dataclass
class SharedQueryEmbedder:
    embed_query: Callable[[str], list[float]]
    cache: dict[str, list[float]] = field(default_factory=dict)

    def get(self, question: str) -> list[float]:
        if question not in self.cache:
            self.cache[question] = self.embed_query(question)
        return self.cache[question]


def filter_questions(questions: list[dict], variant_type: str | None) -> list[dict]:
    if variant_type is None:
        return questions
    selected = [row for row in questions if row.get("variant_type") == variant_type]
    if not selected:
        raise ValueError(f"variant_type={variant_type}の質問がありません")
    return selected


def evaluate_backend_pair(
    questions: list[dict],
    *,
    embed_query: Callable[[str], list[float]],
    chroma_search: Callable[[list[float], int], list],
    qdrant_search: Callable[[list[float], int], list],
) -> tuple[list[dict], list[dict], int]:
    shared = SharedQueryEmbedder(embed_query)

    def chroma_retrieve(query: str, top_k: int):
        return chroma_search(shared.get(query), top_k)

    def qdrant_retrieve(query: str, top_k: int):
        return qdrant_search(shared.get(query), top_k)

    chroma_records = evaluate_retrieval(questions, retrieve_fn=chroma_retrieve)
    qdrant_records = evaluate_retrieval(questions, retrieve_fn=qdrant_retrieve)
    return chroma_records, qdrant_records, len(shared.cache)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_or_create_query_vectors(
    cache_path: Path,
    questions: list[dict],
    *,
    embeddings,
    batch_size: int = 100,
) -> tuple[dict[str, list[float]], int, bool]:
    question_texts = [row["question"] for row in questions]
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if (
            cache.get("embedding_model") == EMBEDDING_MODEL_NAME
            and cache.get("questions") == question_texts
        ):
            return dict(zip(question_texts, cache["vectors"], strict=True)), 0, True
        raise ValueError(f"Embedding cacheの条件が一致しません: {cache_path}")

    vectors = embeddings.embed_documents(
        question_texts,
        batch_size=batch_size,
        task_type="RETRIEVAL_QUERY",
    )
    if len(vectors) != len(question_texts):
        raise ValueError("質問数とEmbedding数が一致しません")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "embedding_model": EMBEDDING_MODEL_NAME,
                "questions": question_texts,
                "vectors": vectors,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(cache_path)
    return (
        dict(zip(question_texts, vectors, strict=True)),
        math.ceil(len(question_texts) / batch_size),
        False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--variant-type")
    parser.add_argument("--chroma-output", type=Path, required=True)
    parser.add_argument("--qdrant-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path, required=True)
    args = parser.parse_args()

    questions = filter_questions(
        load_evaluation_questions(args.input), args.variant_type
    )
    embeddings = get_embeddings()
    chroma = get_vector_store()
    qdrant = QdrantVectorIndex()
    query_vectors, embedding_requests, cache_hit = load_or_create_query_vectors(
        args.embedding_cache,
        questions,
        embeddings=embeddings,
    )
    with redirect_stdout(StringIO()):
        chroma_records, qdrant_records, embedding_calls = evaluate_backend_pair(
            questions,
            embed_query=lambda question: query_vectors[question],
            chroma_search=lambda vector, top_k: (
                chroma.similarity_search_by_vector_with_relevance_scores(
                    vector, k=top_k
                )
            ),
            qdrant_search=lambda vector, top_k: retrieve_by_vector(
                vector, top_k, index=qdrant
            ),
        )
    save_results(chroma_records, args.chroma_output)
    save_results(qdrant_records, args.qdrant_output)
    before = {row["question_id"]: row for row in chroma_records}
    after = {row["question_id"]: row for row in qdrant_records}
    summary, changes = compare_results(before, after)
    manifest = {
        "input": str(args.input),
        "input_sha256": file_sha256(args.input),
        "variant_type": args.variant_type,
        "questions": len(questions),
        "query_vectors": embedding_calls,
        "query_embedding_requests": embedding_requests,
        "embedding_cache_hit": cache_hit,
        "embedding_cache": str(args.embedding_cache),
        "embedding_model": EMBEDDING_MODEL_NAME,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "top_k": TOP_K,
        "chroma_output": str(args.chroma_output),
        "qdrant_output": str(args.qdrant_output),
        "summary": summary,
        "changed_questions": changes,
    }
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
