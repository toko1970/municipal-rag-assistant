"""Create the RAG v2 source-of-truth tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260927_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def uuid_column(name: str, *, primary_key: bool = False) -> sa.Column:
    return sa.Column(
        name, postgresql.UUID(as_uuid=True), primary_key=primary_key, nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "documents",
        uuid_column("id", primary_key=True),
        sa.Column("document_key", sa.String(255), nullable=False, unique=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        created_at(),
    )
    op.create_table(
        "document_versions",
        uuid_column("id", primary_key=True),
        uuid_column("document_id"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        created_at(),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "document_id", "content_hash", name="uq_document_version_hash"
        ),
    )
    op.create_index(
        "ix_document_versions_document_id", "document_versions", ["document_id"]
    )
    op.create_table(
        "content_elements",
        uuid_column("id", primary_key=True),
        uuid_column("document_version_id"),
        sa.Column("element_type", sa.String(50), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column(
            "structured_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("review_status", sa.String(30), nullable=False),
        sa.Column("index_status", sa.String(30), nullable=False),
        created_at(),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "document_version_id", "ordinal", name="uq_element_ordinal"
        ),
    )
    op.create_index(
        "ix_content_elements_document_version_id",
        "content_elements",
        ["document_version_id"],
    )
    op.create_table(
        "visual_assets",
        uuid_column("id", primary_key=True),
        uuid_column("content_element_id"),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text())),
        created_at(),
        sa.ForeignKeyConstraint(
            ["content_element_id"], ["content_elements.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_visual_assets_content_element_id",
        "visual_assets",
        ["content_element_id"],
    )
    op.create_table(
        "embedding_profiles",
        uuid_column("id", primary_key=True),
        sa.Column("profile_key", sa.String(255), nullable=False, unique=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        created_at(),
    )
    op.create_table(
        "rag_requests",
        uuid_column("id", primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        created_at(),
    )
    op.create_table(
        "retrieval_results",
        uuid_column("id", primary_key=True),
        uuid_column("request_id"),
        uuid_column("content_element_id"),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("index_name", sa.String(255), nullable=False),
        created_at(),
        sa.ForeignKeyConstraint(
            ["request_id"], ["rag_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["content_element_id"], ["content_elements.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("request_id", "rank", name="uq_retrieval_request_rank"),
    )
    op.create_index(
        "ix_retrieval_results_request_id", "retrieval_results", ["request_id"]
    )
    op.create_table(
        "generation_results",
        uuid_column("id", primary_key=True),
        uuid_column("request_id"),
        sa.Column("final_label", sa.String(50)),
        sa.Column("display_text", sa.Text()),
        sa.Column("status", sa.String(40), nullable=False),
        created_at(),
        sa.ForeignKeyConstraint(
            ["request_id"], ["rag_requests.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("request_id"),
    )
    op.create_table(
        "generation_attempts",
        uuid_column("id", primary_key=True),
        uuid_column("request_id"),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("response_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("error_summary", sa.Text()),
        created_at(),
        sa.ForeignKeyConstraint(
            ["request_id"], ["rag_requests.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_generation_attempts_request_id", "generation_attempts", ["request_id"]
    )
    op.create_table(
        "classification_attempts",
        uuid_column("id", primary_key=True),
        uuid_column("request_id"),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("factors", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("derived_label", sa.String(50)),
        sa.Column("confidence", sa.Float()),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("error_summary", sa.Text()),
        created_at(),
        sa.ForeignKeyConstraint(
            ["request_id"], ["rag_requests.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_classification_attempts_request_id",
        "classification_attempts",
        ["request_id"],
    )
    op.create_table(
        "answer_claims",
        uuid_column("id", primary_key=True),
        uuid_column("generation_result_id"),
        sa.Column("claim_key", sa.String(100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False),
        created_at(),
        sa.ForeignKeyConstraint(
            ["generation_result_id"],
            ["generation_results.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "generation_result_id", "ordinal", name="uq_claim_ordinal"
        ),
    )
    op.create_index(
        "ix_answer_claims_generation_result_id",
        "answer_claims",
        ["generation_result_id"],
    )
    op.create_table(
        "claim_evidence",
        uuid_column("claim_id", primary_key=True),
        uuid_column("content_element_id", primary_key=True),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["answer_claims.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["content_element_id"], ["content_elements.id"], ondelete="RESTRICT"
        ),
    )
    op.create_table(
        "feedback",
        uuid_column("id", primary_key=True),
        uuid_column("request_id"),
        sa.Column("value", sa.String(50), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        created_at(),
        sa.ForeignKeyConstraint(
            ["request_id"], ["rag_requests.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_feedback_request_id", "feedback", ["request_id"])


def downgrade() -> None:
    for table_name in (
        "feedback",
        "claim_evidence",
        "answer_claims",
        "classification_attempts",
        "generation_attempts",
        "generation_results",
        "retrieval_results",
        "rag_requests",
        "embedding_profiles",
        "visual_assets",
        "content_elements",
        "document_versions",
        "documents",
    ):
        op.drop_table(table_name)
