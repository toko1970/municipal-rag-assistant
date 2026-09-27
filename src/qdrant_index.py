"""Qdrant adapter with stable PostgreSQL content element IDs."""

from __future__ import annotations

from uuid import UUID

from qdrant_client import QdrantClient, models

from config import QDRANT_COLLECTION_NAME, QDRANT_URL
from src.contracts import IndexableElement, SearchHit


class QdrantVectorIndex:
    def __init__(
        self,
        client: QdrantClient | None = None,
        collection_name: str = QDRANT_COLLECTION_NAME,
    ) -> None:
        self.client = client or QdrantClient(url=QDRANT_URL)
        self.collection_name = collection_name

    def ensure_collection(self, vector_size: int) -> None:
        if self.client.collection_exists(self.collection_name):
            collection = self.client.get_collection(self.collection_name)
            configured_size = collection.config.params.vectors.size
            if configured_size != vector_size:
                raise ValueError(
                    "既存Qdrant collectionのvector次元が一致しません: "
                    f"expected={vector_size}, actual={configured_size}"
                )
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=vector_size, distance=models.Distance.COSINE
            ),
        )

    def upsert(
        self,
        elements: list[IndexableElement],
        vectors: list[list[float]],
        embedding_profile: str,
    ) -> None:
        if len(elements) != len(vectors):
            raise ValueError("element数とvector数が一致しません")
        points = []
        for element, vector in zip(elements, vectors, strict=True):
            payload = {
                "element_id": str(element.id),
                "document_id": str(element.document_id),
                "version_id": str(element.version_id),
                "document_name": element.document_name,
                "heading": element.heading,
                "content": element.content,
                "element_type": element.element_type,
                "page_number": element.page_number,
                "embedding_profile": embedding_profile,
                "metadata": element.metadata,
            }
            points.append(
                models.PointStruct(id=str(element.id), vector=vector, payload=payload)
            )
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def search(self, query_vector: list[float], limit: int) -> list[SearchHit]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )
        hits: list[SearchHit] = []
        for rank, point in enumerate(response.points, start=1):
            payload = point.payload or {}
            element = IndexableElement(
                id=UUID(str(payload["element_id"])),
                document_id=UUID(str(payload["document_id"])),
                version_id=UUID(str(payload["version_id"])),
                document_name=str(payload.get("document_name", "")),
                heading=str(payload.get("heading", "")),
                content=str(payload.get("content", "")),
                element_type=str(payload.get("element_type", "text")),
                page_number=payload.get("page_number"),
                metadata=dict(payload.get("metadata") or {}),
            )
            hits.append(SearchHit(element=element, score=float(point.score), rank=rank))
        return hits

    def list_point_ids(self) -> set[UUID]:
        if not self.client.collection_exists(self.collection_name):
            return set()
        point_ids: set[UUID] = set()
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.update(UUID(str(point.id)) for point in points)
            if offset is None:
                return point_ids
