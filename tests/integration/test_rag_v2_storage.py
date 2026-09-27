from pathlib import Path
from uuid import uuid4

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
)
from src.persistence.repositories import (
    PostgresDocumentRepository,
    PostgresEventLogger,
)
from src.qdrant_index import QdrantVectorIndex


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
