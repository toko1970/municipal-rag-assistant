"""PostgreSQL repositories used by the RAG v2 application boundary."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import QDRANT_COLLECTION_NAME
from src.contracts import IndexableElement, SearchHit
from src.persistence.models import (
    AnswerClaimRow,
    ClaimEvidenceRow,
    ClassificationAttemptRow,
    ContentElementRow,
    DocumentRow,
    DocumentVersionRow,
    EmbeddingProfileRow,
    FeedbackRow,
    GenerationAttemptRow,
    GenerationResultRow,
    RagRequestRow,
    RetrievalResultRow,
)


class PostgresDocumentRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def upsert_markdown_elements(
        self, source_path: str, document_name: str, elements: list[IndexableElement]
    ) -> list[IndexableElement]:
        if not elements:
            return []
        first = elements[0]
        document_key = str(first.metadata["document_key"])
        content_hash = str(first.metadata["content_hash"])

        with self.session_factory() as session, session.begin():
            document = session.get(DocumentRow, first.document_id)
            if document is None:
                session.add(
                    DocumentRow(
                        id=first.document_id,
                        document_key=document_key,
                        title=document_name,
                        source_type="markdown",
                    )
                )
            else:
                document.title = document_name

            version = session.get(DocumentVersionRow, first.version_id)
            if version is None:
                session.add(
                    DocumentVersionRow(
                        id=first.version_id,
                        document_id=first.document_id,
                        content_hash=content_hash,
                        source_path=source_path,
                        status="READY",
                    )
                )

            for ordinal, element in enumerate(elements):
                row = session.get(ContentElementRow, element.id)
                if row is None:
                    session.add(
                        ContentElementRow(
                            id=element.id,
                            document_version_id=element.version_id,
                            element_type=element.element_type,
                            ordinal=ordinal,
                            page_number=element.page_number,
                            heading=element.heading,
                            content_text=element.content,
                            structured_data=element.metadata,
                            review_status="READY",
                            index_status="PENDING",
                        )
                    )
                else:
                    row.heading = element.heading
                    row.content_text = element.content
                    row.structured_data = element.metadata
                    row.review_status = "READY"
        return elements

    def get_elements(self, element_ids: list[UUID]) -> list[IndexableElement]:
        if not element_ids:
            return []
        with self.session_factory() as session:
            rows = session.scalars(
                select(ContentElementRow).where(ContentElementRow.id.in_(element_ids))
            ).all()
            versions = {
                version.id: version
                for version in session.scalars(
                    select(DocumentVersionRow).where(
                        DocumentVersionRow.id.in_(
                            {row.document_version_id for row in rows}
                        )
                    )
                ).all()
            }
            documents = {
                document.id: document
                for document in session.scalars(
                    select(DocumentRow).where(
                        DocumentRow.id.in_(
                            {version.document_id for version in versions.values()}
                        )
                    )
                ).all()
            }
            by_id = {row.id: row for row in rows}
            result: list[IndexableElement] = []
            for element_id in element_ids:
                row = by_id.get(element_id)
                if row is None:
                    continue
                version = versions[row.document_version_id]
                document = documents[version.document_id]
                result.append(
                    IndexableElement(
                        id=row.id,
                        document_id=document.id,
                        version_id=version.id,
                        document_name=document.title,
                        heading=row.heading,
                        content=row.content_text,
                        element_type=row.element_type,
                        page_number=row.page_number,
                        metadata=dict(row.structured_data),
                    )
                )
            return result

    def mark_index_status(self, element_ids: list[UUID], status: str) -> None:
        with self.session_factory() as session, session.begin():
            rows = session.scalars(
                select(ContentElementRow).where(ContentElementRow.id.in_(element_ids))
            ).all()
            for row in rows:
                row.index_status = status

    def list_indexed_element_ids(self) -> set[UUID]:
        with self.session_factory() as session:
            return set(
                session.scalars(
                    select(ContentElementRow.id).where(
                        ContentElementRow.index_status == "INDEXED"
                    )
                ).all()
            )

    def upsert_embedding_profile(
        self,
        profile_key: str,
        provider: str,
        model: str,
        dimensions: int,
        configuration: dict,
    ) -> UUID:
        with self.session_factory() as session, session.begin():
            existing = session.scalar(
                select(EmbeddingProfileRow).where(
                    EmbeddingProfileRow.profile_key == profile_key
                )
            )
            if existing is None:
                existing = EmbeddingProfileRow(
                    id=uuid4(),
                    profile_key=profile_key,
                    provider=provider,
                    model=model,
                    dimensions=dimensions,
                    configuration=configuration,
                    active=True,
                )
                session.add(existing)
            else:
                existing.dimensions = dimensions
                existing.configuration = configuration
                existing.active = True
            return existing.id


class PostgresEventLogger:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def start_request(self, question: str) -> UUID:
        request_id = uuid4()
        with self.session_factory() as session, session.begin():
            session.add(RagRequestRow(id=request_id, question=question))
        return request_id

    def record_retrieval(self, request_id: UUID, hits: list[SearchHit]) -> None:
        with self.session_factory() as session, session.begin():
            for hit in hits:
                session.add(
                    RetrievalResultRow(
                        id=uuid4(),
                        request_id=request_id,
                        content_element_id=hit.element.id,
                        rank=hit.rank,
                        score=hit.score,
                        index_name=QDRANT_COLLECTION_NAME,
                    )
                )

    def record_feedback(
        self, request_id: UUID, value: str, comment: str = ""
    ) -> UUID:
        feedback_id = uuid4()
        with self.session_factory() as session, session.begin():
            session.add(
                FeedbackRow(
                    id=feedback_id,
                    request_id=request_id,
                    value=value,
                    comment=comment,
                )
            )
        return feedback_id

    def record_generation_attempt(
        self,
        request_id: UUID,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        response_data: dict | None,
        input_tokens: int,
        output_tokens: int,
        status: str,
        error_summary: str | None = None,
    ) -> UUID:
        attempt_id = uuid4()
        with self.session_factory() as session, session.begin():
            session.add(
                GenerationAttemptRow(
                    id=attempt_id,
                    request_id=request_id,
                    provider=provider,
                    model=model,
                    prompt_version=prompt_version,
                    response_data=response_data,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status=status,
                    error_summary=error_summary,
                )
            )
        return attempt_id

    def record_classification_attempt(
        self,
        request_id: UUID,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        factors: dict | None,
        derived_label: str | None,
        confidence: float | None,
        status: str,
        fallback_used: bool = False,
        error_summary: str | None = None,
    ) -> UUID:
        attempt_id = uuid4()
        with self.session_factory() as session, session.begin():
            session.add(
                ClassificationAttemptRow(
                    id=attempt_id,
                    request_id=request_id,
                    provider=provider,
                    model=model,
                    prompt_version=prompt_version,
                    factors=factors,
                    derived_label=derived_label,
                    confidence=confidence,
                    status=status,
                    fallback_used=fallback_used,
                    error_summary=error_summary,
                )
            )
        return attempt_id

    def record_answer_result(
        self,
        request_id: UUID,
        *,
        label: str,
        display_text: str,
        claims: list[dict],
    ) -> UUID:
        result_id = uuid4()
        with self.session_factory() as session, session.begin():
            session.add(
                GenerationResultRow(
                    id=result_id,
                    request_id=request_id,
                    final_label=label,
                    display_text=display_text,
                    status="SUCCESS",
                )
            )
            session.flush()
            for claim in claims:
                claim_id = uuid4()
                session.add(
                    AnswerClaimRow(
                        id=claim_id,
                        generation_result_id=result_id,
                        claim_key=claim["claim_id"],
                        ordinal=claim["ordinal"],
                        text=claim["text"],
                        supported=True,
                    )
                )
                session.flush()
                for evidence_id in claim["evidence_element_ids"]:
                    session.add(
                        ClaimEvidenceRow(
                            claim_id=claim_id,
                            content_element_id=evidence_id,
                        )
                    )
        return result_id
