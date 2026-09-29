from uuid import uuid4

from eval.bm25_hybrid_retriever import (
    BM25Index,
    create_sudachi_tokenizer,
    reciprocal_rank_fusion,
)
from src.contracts import IndexableElement, SearchHit


def _element(heading: str, content: str) -> IndexableElement:
    return IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="届出・手続きマニュアル",
        heading=heading,
        content=content,
        metadata={"見出し1": heading, "document_id": "DOC-004"},
    )


def test_sudachi_mode_c_keeps_domain_compounds() -> None:
    tokens = create_sudachi_tokenizer()("扶養親族変更届の提出期限は15日以内です。")

    assert "扶養親族" in tokens
    assert "変更届" in tokens
    assert "15" in tokens
    assert "以内" in tokens


def test_bm25_uses_heading_and_content_for_exact_procedure_terms() -> None:
    address = _element("住所変更届", "転居した場合は14日以内に提出する。")
    commute = _element("通勤経路変更届", "変更日から10日以内に提出する。")
    index = BM25Index([commute, address], tokenize=create_sudachi_tokenizer())

    hits = index.search("転居後の住所変更届は何日以内ですか？", limit=2)

    assert hits[0].element.id == address.id


def test_rrf_can_promote_sparse_hit_without_discarding_dense_hit() -> None:
    dense_first = _element("通勤手当", "支給を停止する。")
    sparse_first = _element("住所変更届", "14日以内に提出する。")
    dense_hits = [
        SearchHit(dense_first, 0.9, 1),
        SearchHit(sparse_first, 0.5, 2),
    ]
    sparse_index = BM25Index(
        [dense_first, sparse_first], tokenize=create_sudachi_tokenizer()
    )
    sparse_hits = sparse_index.search("住所変更届", limit=2)

    fused = reciprocal_rank_fusion(dense_hits, sparse_hits, limit=2, rrf_k=60)

    assert {hit.element.id for hit in fused} == {dense_first.id, sparse_first.id}
    assert fused[0].element.id == sparse_first.id
