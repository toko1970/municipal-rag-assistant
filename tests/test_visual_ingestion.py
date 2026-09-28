import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.asset_store import LocalAssetStore
from src.visual_ingestion import (
    ReviewRequiredError,
    ingest_visual_pdf,
    render_pdf_page,
    visual_search_text,
)


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "eval/visual_fixtures/documents/flowchart_dev_001.pdf"
GOLD = ROOT / "eval/visual_fixtures/gold/flowchart_dev_001.json"


class FakeRepository:
    def __init__(self) -> None:
        self.element = None
        self.asset = None
        self.statuses = []
        self.profile = None

    def upsert_visual_element(self, **kwargs):
        self.element = kwargs["element"]
        self.asset = kwargs["asset"]
        return self.element

    def mark_index_status(self, element_ids, status):
        self.statuses.append((element_ids, status))

    def upsert_embedding_profile(self, **kwargs):
        self.profile = kwargs
        return uuid4()


class FakeIndex:
    def __init__(self) -> None:
        self.vector_size = None
        self.upserted = None

    def ensure_collection(self, vector_size):
        self.vector_size = vector_size

    def upsert(self, elements, vectors, embedding_profile):
        self.upserted = (elements, vectors, embedding_profile)


class FakeEmbeddings:
    def embed_documents(self, texts, task_type):
        assert task_type == "RETRIEVAL_DOCUMENT"
        assert "申請者へ差戻し" in texts[0]
        return [[0.1, 0.2, 0.3]]


def extraction_for_rendered_page() -> dict:
    extraction = json.loads(GOLD.read_text(encoding="utf-8"))
    extraction["source_image_sha256"] = render_pdf_page(PDF, 1).sha256
    return extraction


def test_visual_search_text_preserves_nodes_edges_and_conditions() -> None:
    text = visual_search_text(extraction_for_rendered_page())
    assert "不備があるか" in text
    assert "申請者へ差戻し [あり]" in text
    assert "給与システムへ登録 [なし]" in text


def test_ingestion_stops_before_storage_when_review_is_required(tmp_path) -> None:
    repository = FakeRepository()
    with pytest.raises(ReviewRequiredError):
        ingest_visual_pdf(
            pdf_path=PDF,
            document_key="VIS-FLOW-001",
            document_name="通勤手当申請処理フロー",
            extraction=extraction_for_rendered_page(),
            reviewed=False,
            repository=repository,
            vector_index=FakeIndex(),
            asset_store=LocalAssetStore(tmp_path),
            embeddings=FakeEmbeddings(),
        )
    assert repository.element is None
    assert not list(tmp_path.rglob("*.png"))


def test_reviewed_visual_pdf_is_stored_and_indexed_with_stable_id(tmp_path) -> None:
    repository = FakeRepository()
    index = FakeIndex()
    kwargs = {
        "pdf_path": PDF,
        "document_key": "VIS-FLOW-001",
        "document_name": "通勤手当申請処理フロー",
        "extraction": extraction_for_rendered_page(),
        "reviewed": True,
        "repository": repository,
        "vector_index": index,
        "asset_store": LocalAssetStore(tmp_path),
        "embeddings": FakeEmbeddings(),
    }
    first = ingest_visual_pdf(**kwargs)
    second = ingest_visual_pdf(**{**kwargs, "extraction": copy.deepcopy(kwargs["extraction"])})

    assert first["element_id"] == second["element_id"]
    assert first["review_status"] == "READY"
    assert first["index_status"] == "INDEXED"
    assert repository.asset.sha256 == kwargs["extraction"]["source_image_sha256"]
    assert repository.element.page_number == 1
    assert repository.element.element_type == "flowchart"
    assert index.vector_size == 3
    assert repository.statuses[-1][1] == "INDEXED"
    assert len(list(tmp_path.rglob("*.png"))) == 1


def test_extraction_image_hash_mismatch_is_rejected(tmp_path) -> None:
    extraction = extraction_for_rendered_page()
    extraction["source_image_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        ingest_visual_pdf(
            pdf_path=PDF,
            document_key="VIS-FLOW-001",
            document_name="通勤手当申請処理フロー",
            extraction=extraction,
            reviewed=True,
            repository=FakeRepository(),
            vector_index=FakeIndex(),
            asset_store=LocalAssetStore(tmp_path),
            embeddings=FakeEmbeddings(),
        )
