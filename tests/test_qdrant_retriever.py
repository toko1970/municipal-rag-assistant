from types import SimpleNamespace
from uuid import uuid4

from src.contracts import IndexableElement, SearchHit
from src.qdrant_index import QdrantVectorIndex


def test_qdrant_cloud_api_key_is_forwarded(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.qdrant_index.QdrantClient", Client)
    monkeypatch.setattr("src.qdrant_index.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("src.qdrant_index.QDRANT_API_KEY", "secret-key")

    index = QdrantVectorIndex(collection_name="test")

    assert captured == {
        "url": "https://example.qdrant.io",
        "api_key": "secret-key",
    }
    assert index.collection_name == "test"


def test_qdrant_evaluation_adapter_preserves_original_document_metadata(monkeypatch):
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="給与制度規程",
        heading="3. 給与支給日",
        content="給与は毎月21日に支給する。",
        metadata={"document_id": "DOC-001", "見出し1": "給与制度規程"},
    )
    embeddings = SimpleNamespace(embed_query=lambda _query: [1.0, 0.0])
    index = SimpleNamespace(
        search=lambda _vector, limit: [SearchHit(element, 0.91, 1)][:limit]
    )
    monkeypatch.setattr(
        "eval.qdrant_retriever.get_qdrant_dependencies",
        lambda: (embeddings, index),
    )

    from eval.qdrant_retriever import retrieve_documents_with_score

    results = retrieve_documents_with_score("支給日は？", top_k=5)

    document, score = results[0]
    assert score == 0.91
    assert document.metadata["document_id"] == "DOC-001"
    assert document.metadata["見出し1"] == "給与制度規程"
    assert document.metadata["見出し2"] == "3. 給与支給日"
    assert document.metadata["chunk_id"] == str(element.id)


def test_qdrant_index_round_trips_version_metadata():
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="給与制度規程",
        heading="支給日",
        content="毎月21日に支給する。",
        metadata={
            "effective_date": "2025-04-01",
            "version": "1.0",
            "document_role": "primary",
            "is_primary": True,
            "content_hash": "b" * 64,
        },
    )

    class Client:
        def upsert(self, *, points, **_kwargs):
            self.payload = points[0].payload

        def query_points(self, **_kwargs):
            return SimpleNamespace(
                points=[SimpleNamespace(payload=self.payload, score=0.9)]
            )

    index = QdrantVectorIndex(client=Client(), collection_name="test")
    index.upsert([element], [[0.1, 0.2]], "test-profile")
    hit = index.search([0.1, 0.2], 1)[0]

    assert hit.element.version_id == element.version_id
    assert hit.element.metadata["effective_date"] == "2025-04-01"
    assert hit.element.metadata["version"] == "1.0"
    assert hit.element.metadata["document_role"] == "primary"
    assert hit.element.metadata["is_primary"] is True
    assert hit.element.metadata["content_hash"] == "b" * 64
