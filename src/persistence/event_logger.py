"""PostgreSQL repositories used by the RAG v2 application boundary."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from config import QDRANT_COLLECTION_NAME
from src.contracts import SearchHit
from src.persistence.models import (
    AnswerClaimRow,
    ClaimEvidenceRow,
    ClassificationAttemptRow,
    FeedbackRow,
    GenerationAttemptRow,
    GenerationResultRow,
    RagRequestRow,
    RetrievalResultRow,
)


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

    def record_feedback(self, request_id: UUID, value: str, comment: str = "") -> UUID:
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
        label: str | None,
        display_text: str,
        claims: list[dict],
        status: str = "SUCCESS",
    ) -> UUID:
        result_id = uuid4()
        with self.session_factory() as session, session.begin():
            session.add(
                GenerationResultRow(
                    id=result_id,
                    request_id=request_id,
                    final_label=label,
                    display_text=display_text,
                    status=status,
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
