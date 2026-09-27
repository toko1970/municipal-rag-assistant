"""Evaluation adapter exposing Qdrant results in the legacy evaluator shape."""

from __future__ import annotations

from functools import lru_cache

from langchain_core.documents import Document

from config import TOP_K
from src.embeddings import get_embeddings
from src.qdrant_index import QdrantVectorIndex


@lru_cache(maxsize=1)
def get_qdrant_dependencies():
    return get_embeddings(), QdrantVectorIndex()


def retrieve_documents_with_score(query: str, top_k: int = TOP_K):
    embeddings, index = get_qdrant_dependencies()
    hits = index.search(embeddings.embed_query(query), limit=top_k)
    results = []
    for hit in hits:
        metadata = {
            **hit.element.metadata,
            "document_id": hit.element.metadata.get(
                "document_id", str(hit.element.document_id)
            ),
            "document_name": hit.element.document_name,
            "見出し2": hit.element.heading,
            "chunk_id": str(hit.element.id),
        }
        results.append(
            (
                Document(page_content=hit.element.content, metadata=metadata),
                hit.score,
            )
        )
    return results
