import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from config import QDRANT_URL
from src.ingestion import build_markdown_elements
from src.persistence.database import get_engine
from src.persistence.models import (
    AnswerClaimRow,
    ClaimEvidenceRow,
    ClassificationAttemptRow,
    ContentElementRow,
    DocumentRow,
    EmbeddingProfileRow,
    FeedbackRow,
    GenerationAttemptRow,
    GenerationResultRow,
    RagRequestRow,
    RetrievalResultRow,
    VisualAssetRow,
)
from src.persistence.repositories import (
    PostgresDocumentRepository,
    PostgresEventLogger,
)
from src.qdrant_index import QdrantVectorIndex
from src.asset_store import LocalAssetStore
from src.visual_ingestion import ingest_visual_pdf, render_pdf_page


ROOT = Path(__file__).resolve().parents[2]


class FakeVisualEmbeddings:
    def embed_documents(self, texts, task_type):
        assert task_type == "RETRIEVAL_DOCUMENT"
        assert "申請者へ差戻し" in texts[0]
        return [[1.0, 0.0, 0.0]]


class StableFakeEmbeddings:
    def embed_documents(self, texts, task_type):
        assert task_type == "RETRIEVAL_DOCUMENT"
        assert len(texts) == 1
        assert texts[0]
        return [[1.0, 0.0, 0.0]]


@pytest.mark.integration
def test_postgres_qdrant_and_event_log_round_trip(tmp_path: Path) -> None:
    document_key = f"integration-{uuid4()}"
    path = tmp_path / "integration.md"
    path.write_text(
        "---\n"
        f"document_id: {document_key}\n"
        "document_name: 統合試験通知\n"
        "---\n"
        "# 通知\n\n## 支給日\n\n給与は毎月21日に支給します。\n",
        encoding="utf-8",
    )
    elements = build_markdown_elements(path)
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    repository = PostgresDocumentRepository(factory)
    logger = PostgresEventLogger(factory)
    collection_name = f"integration_{uuid4().hex}"
    client = QdrantClient(url=QDRANT_URL)
    index = QdrantVectorIndex(client=client, collection_name=collection_name)
    request_id = None

    try:
        repository.upsert_markdown_elements(str(path), "統合試験通知", elements)
        repository.upsert_markdown_elements(str(path), "統合試験通知", elements)
        repository.upsert_embedding_profile(
            profile_key="fake:test:3",
            provider="fake",
            model="test",
            dimensions=3,
            configuration={"purpose": "integration"},
        )
        vectors = [[1.0, 0.0, 0.0] for _ in elements]
        index.ensure_collection(3)
        index.upsert(elements, vectors, "fake:test:3")
        hits = index.search([1.0, 0.0, 0.0], limit=3)

        request_id = logger.start_request("給与支給日はいつですか？")
        logger.record_retrieval(request_id, hits)
        logger.record_generation_attempt(
            request_id,
            provider="fake",
            model="generator-test",
            prompt_version="answer-claims-v1",
            response_data={"schema_version": "1.0"},
            input_tokens=10,
            output_tokens=5,
            status="SUCCESS",
        )
        logger.record_classification_attempt(
            request_id,
            provider="fake",
            model="classifier-test",
            prompt_version="answer-classification-v1",
            factors={"retrieval_sufficient": True},
            derived_label="根拠十分",
            confidence=0.95,
            status="SUCCESS",
        )
        logger.record_answer_result(
            request_id,
            label="根拠十分",
            display_text="回答分類: 根拠十分\n\n回答:\n- 給与は毎月21日に支給されます。",
            claims=[
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "給与は毎月21日に支給されます。",
                    "evidence_element_ids": [elements[0].id],
                }
            ],
        )
        logger.record_feedback(request_id, "採用した", "統合試験")

        with factory() as session:
            assert session.scalar(
                select(func.count()).select_from(DocumentRow).where(
                    DocumentRow.document_key == document_key
                )
            ) == 1
            assert session.scalar(
                select(func.count()).select_from(ContentElementRow).where(
                    ContentElementRow.id.in_([item.id for item in elements])
                )
            ) == len(elements)
            assert session.get(RagRequestRow, request_id) is not None
            assert session.scalar(
                select(func.count()).select_from(RetrievalResultRow).where(
                    RetrievalResultRow.request_id == request_id
                )
            ) == len(hits)
            assert session.scalar(
                select(func.count()).select_from(FeedbackRow).where(
                    FeedbackRow.request_id == request_id
                )
            ) == 1
            assert session.scalar(
                select(func.count()).select_from(GenerationAttemptRow).where(
                    GenerationAttemptRow.request_id == request_id
                )
            ) == 1
            assert session.scalar(
                select(func.count()).select_from(ClassificationAttemptRow).where(
                    ClassificationAttemptRow.request_id == request_id
                )
            ) == 1
            generation_result_id = session.scalar(
                select(GenerationResultRow.id).where(
                    GenerationResultRow.request_id == request_id
                )
            )
            claim_id = session.scalar(
                select(AnswerClaimRow.id).where(
                    AnswerClaimRow.generation_result_id == generation_result_id
                )
            )
            assert session.get(ClaimEvidenceRow, (claim_id, elements[0].id)) is not None
        assert hits[0].element.id == elements[0].id
        assert hits[0].element.document_name == "統合試験通知"
    finally:
        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
        with factory() as session, session.begin():
            if request_id is not None:
                session.execute(delete(RagRequestRow).where(RagRequestRow.id == request_id))
            session.execute(
                delete(DocumentRow).where(DocumentRow.id == elements[0].document_id)
            )
            session.execute(
                delete(EmbeddingProfileRow).where(
                    EmbeddingProfileRow.profile_key == "fake:test:3"
                )
            )


@pytest.mark.integration
def test_visual_pdf_round_trip_is_idempotent(tmp_path: Path) -> None:
    pdf_path = ROOT / "eval/visual_fixtures/documents/flowchart_dev_001.pdf"
    extraction_path = ROOT / "eval/visual_fixtures/gold/flowchart_dev_001.json"
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    extraction["source_image_sha256"] = render_pdf_page(pdf_path, 1).sha256
    document_key = f"visual-integration-{uuid4()}"
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    repository = PostgresDocumentRepository(factory)
    collection_name = f"visual_integration_{uuid4().hex}"
    client = QdrantClient(url=QDRANT_URL)
    index = QdrantVectorIndex(client=client, collection_name=collection_name)
    kwargs = {
        "pdf_path": pdf_path,
        "document_key": document_key,
        "document_name": "通勤手当申請処理フロー",
        "extraction": extraction,
        "reviewed": True,
        "repository": repository,
        "vector_index": index,
        "asset_store": LocalAssetStore(tmp_path / "assets"),
        "embeddings": FakeVisualEmbeddings(),
    }
    element_id = None

    try:
        first = ingest_visual_pdf(**kwargs)
        second = ingest_visual_pdf(**kwargs)
        element_id = first["element_id"]

        with factory() as session:
            document = session.scalar(
                select(DocumentRow).where(DocumentRow.document_key == document_key)
            )
            assert document is not None
            assert session.scalar(
                select(func.count()).select_from(ContentElementRow).where(
                    ContentElementRow.id == element_id
                )
            ) == 1
            asset = session.scalar(
                select(VisualAssetRow).where(
                    VisualAssetRow.content_element_id == element_id
                )
            )
            assert asset is not None
            assert asset.sha256 == extraction["source_image_sha256"]
            loaded_asset = repository.get_visual_assets([UUID(element_id)])[0]
            assert loaded_asset.element_id == UUID(element_id)
            assert loaded_asset.read_verified() == Path(asset.local_path).read_bytes()
        assert first["element_id"] == second["element_id"]
        assert len(list((tmp_path / "assets").rglob("*.png"))) == 1
        hits = index.search([1.0, 0.0, 0.0], limit=1)
        assert str(hits[0].element.id) == element_id
        assert hits[0].element.element_type == "flowchart"
    finally:
        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
        with factory() as session, session.begin():
            document = session.scalar(
                select(DocumentRow).where(DocumentRow.document_key == document_key)
            )
            if document is not None:
                session.delete(document)
            session.execute(
                delete(EmbeddingProfileRow).where(
                    EmbeddingProfileRow.profile_key
                    == "gemini:gemini-embedding-001:visual-description-v1"
                )
            )


@pytest.mark.integration
def test_all_reviewed_visual_fixtures_complete_quality_streak(
    tmp_path: Path,
) -> None:
    manifest = json.loads(
        (
            ROOT / "eval/visual_fixtures/manifests/development_manifest.json"
        ).read_text(encoding="utf-8")
    )
    run_key = uuid4().hex
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    repository = PostgresDocumentRepository(factory)
    collection_name = f"visual_streak_{run_key}"
    client = QdrantClient(url=QDRANT_URL)
    index = QdrantVectorIndex(client=client, collection_name=collection_name)
    document_keys: list[str] = []
    element_ids: list[str] = []

    try:
        for fixture in manifest["fixtures"]:
            fixture_id = fixture["fixture_id"]
            pdf_path = ROOT / fixture["document"]["path"]
            extraction = json.loads(
                (ROOT / fixture["gold"]["path"]).read_text(encoding="utf-8")
            )
            extraction["source_image_sha256"] = render_pdf_page(
                pdf_path, extraction["page"]
            ).sha256
            document_key = f"visual-streak-{run_key}-{fixture_id}"
            document_keys.append(document_key)
            kwargs = {
                "pdf_path": pdf_path,
                "document_key": document_key,
                "document_name": extraction["title"],
                "extraction": extraction,
                "reviewed": True,
                "repository": repository,
                "vector_index": index,
                "asset_store": LocalAssetStore(tmp_path / "assets"),
                "embeddings": StableFakeEmbeddings(),
            }
            first = ingest_visual_pdf(**kwargs)
            second = ingest_visual_pdf(**kwargs)
            assert first["element_id"] == second["element_id"]
            element_ids.append(first["element_id"])

        with factory() as session:
            assert session.scalar(
                select(func.count()).select_from(DocumentRow).where(
                    DocumentRow.document_key.in_(document_keys)
                )
            ) == 6
            assert session.scalar(
                select(func.count()).select_from(ContentElementRow).where(
                    ContentElementRow.id.in_(element_ids)
                )
            ) == 6
            assert session.scalar(
                select(func.count()).select_from(VisualAssetRow).where(
                    VisualAssetRow.content_element_id.in_(element_ids)
                )
            ) == 6
        assert len(index.list_point_ids()) == 6
        assert len(list((tmp_path / "assets").rglob("*.png"))) == 6
    finally:
        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
        with factory() as session, session.begin():
            documents = session.scalars(
                select(DocumentRow).where(DocumentRow.document_key.in_(document_keys))
            ).all()
            for document in documents:
                session.delete(document)
            session.execute(
                delete(EmbeddingProfileRow).where(
                    EmbeddingProfileRow.profile_key
                    == "gemini:gemini-embedding-001:visual-description-v1"
                )
            )
