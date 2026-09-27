from types import SimpleNamespace
from uuid import uuid4

from src.contracts import IndexableElement, SearchHit


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
