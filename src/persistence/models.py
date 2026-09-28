"""Relational source-of-truth schema for documents and RAG events."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentRow(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    document_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)


class DocumentVersionRow(TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "content_hash", name="uq_document_version_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="READY")


class ContentElementRow(TimestampMixin, Base):
    __tablename__ = "content_elements"
    __table_args__ = (
        UniqueConstraint("document_version_id", "ordinal", name="uq_element_ordinal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    element_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="READY"
    )
    index_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )


class VisualAssetRow(TimestampMixin, Base):
    __tablename__ = "visual_assets"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    content_element_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_elements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class EmbeddingProfileRow(TimestampMixin, Base):
    __tablename__ = "embedding_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    profile_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RagRequestRow(TimestampMixin, Base):
    __tablename__ = "rag_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)


class RetrievalResultRow(TimestampMixin, Base):
    __tablename__ = "retrieval_results"
    __table_args__ = (
        UniqueConstraint("request_id", "rank", name="uq_retrieval_request_rank"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("rag_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_element_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_elements.id", ondelete="RESTRICT"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    index_name: Mapped[str] = mapped_column(String(255), nullable=False)


class GenerationResultRow(TimestampMixin, Base):
    __tablename__ = "generation_results"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("rag_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    final_label: Mapped[str | None] = mapped_column(String(50))
    display_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class GenerationAttemptRow(TimestampMixin, Base):
    __tablename__ = "generation_attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("rag_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    response_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)


class ClassificationAttemptRow(TimestampMixin, Base):
    __tablename__ = "classification_attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("rag_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    factors: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    derived_label: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_summary: Mapped[str | None] = mapped_column(Text)


class AnswerClaimRow(TimestampMixin, Base):
    __tablename__ = "answer_claims"
    __table_args__ = (
        UniqueConstraint("generation_result_id", "ordinal", name="uq_claim_ordinal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    generation_result_id: Mapped[UUID] = mapped_column(
        ForeignKey("generation_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_key: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ClaimEvidenceRow(Base):
    __tablename__ = "claim_evidence"

    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer_claims.id", ondelete="CASCADE"), primary_key=True
    )
    content_element_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_elements.id", ondelete="RESTRICT"), primary_key=True
    )


class FeedbackRow(TimestampMixin, Base):
    __tablename__ = "feedback"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("rag_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
