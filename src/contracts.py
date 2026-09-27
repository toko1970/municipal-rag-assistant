"""Provider boundaries for the portfolio RAG v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class IndexableElement:
    id: UUID
    document_id: UUID
    version_id: UUID
    document_name: str
    heading: str
    content: str
    element_type: str = "text"
    page_number: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchHit:
    element: IndexableElement
    score: float
    rank: int


class DocumentRepository(Protocol):
    def upsert_markdown_elements(
        self, source_path: str, document_name: str, elements: list[IndexableElement]
    ) -> list[IndexableElement]: ...

    def get_elements(self, element_ids: list[UUID]) -> list[IndexableElement]: ...


class VectorIndex(Protocol):
    def ensure_collection(self, vector_size: int) -> None: ...

    def upsert(
        self,
        elements: list[IndexableElement],
        vectors: list[list[float]],
        embedding_profile: str,
    ) -> None: ...

    def search(self, query_vector: list[float], limit: int) -> list[SearchHit]: ...


class EventLogger(Protocol):
    def start_request(self, question: str) -> UUID: ...

    def record_retrieval(self, request_id: UUID, hits: list[SearchHit]) -> None: ...

    def record_feedback(
        self, request_id: UUID, value: str, comment: str = ""
    ) -> UUID: ...
