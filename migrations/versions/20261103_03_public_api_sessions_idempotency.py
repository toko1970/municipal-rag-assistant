"""Add anonymous API sessions, idempotency keys, and atomic quotas."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261103_03"
down_revision: str | None = "20260928_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicate_feedback = connection.execute(
        sa.text(
            "SELECT request_id FROM feedback GROUP BY request_id "
            "HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate_feedback is not None:
        raise RuntimeError(
            "Cannot add one-feedback-per-request constraint: existing duplicate request_id rows found"
        )

    op.add_column(
        "rag_requests", sa.Column("session_hmac", sa.String(64), nullable=True)
    )
    op.add_column(
        "rag_requests",
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rag_requests_session_hmac", "rag_requests", ["session_hmac"])

    op.add_column(
        "generation_attempts",
        sa.Column("usage_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.add_column(
        "feedback",
        sa.Column(
            "generation_result_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_feedback_generation_result_id",
        "feedback",
        "generation_results",
        ["generation_result_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        sa.text(
            "UPDATE feedback AS f SET generation_result_id = gr.id "
            "FROM generation_results AS gr WHERE gr.request_id = f.request_id"
        )
    )
    op.create_unique_constraint("uq_feedback_request", "feedback", ["request_id"])
    op.create_unique_constraint(
        "uq_feedback_generation_result", "feedback", ["generation_result_id"]
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_hmac", sa.String(64), nullable=False),
        sa.Column("session_hmac", sa.String(64), nullable=False),
        sa.Column("submit_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["rag_requests.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "session_hmac", "key_hmac", name="uq_idempotency_session_key"
        ),
        sa.UniqueConstraint("request_id", name="uq_idempotency_request"),
        sa.CheckConstraint(
            "state IN ('ISSUED', 'IN_PROGRESS', 'COMPLETE', 'FAILED', 'INTERRUPTED', 'EXPIRED')",
            name="ck_idempotency_key_state",
        ),
    )
    op.create_index(
        "ix_idempotency_keys_session_hmac", "idempotency_keys", ["session_hmac"]
    )
    op.create_index(
        "ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"]
    )
    op.create_index(
        "uq_idempotency_one_issued_per_session",
        "idempotency_keys",
        ["session_hmac"],
        unique=True,
        postgresql_where=sa.text("state = 'ISSUED'"),
    )

    op.create_table(
        "quota_buckets",
        sa.Column("bucket_date", sa.Date(), nullable=False),
        sa.Column("bucket_type", sa.String(40), nullable=False),
        sa.Column("bucket_key", sa.String(64), nullable=False),
        sa.Column("reserved_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("limit_count", sa.Integer(), nullable=False),
        sa.Column("disabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("bucket_date", "bucket_type", "bucket_key"),
        sa.CheckConstraint("reserved_count >= 0", name="ck_quota_reserved_nonnegative"),
        sa.CheckConstraint("limit_count > 0", name="ck_quota_limit_positive"),
        sa.CheckConstraint(
            "bucket_type IN ('QUESTION_GLOBAL', 'QUESTION_SESSION', "
            "'FEEDBACK_GLOBAL', 'FEEDBACK_SESSION', "
            "'IDEMPOTENCY_KEY_GLOBAL', 'IDEMPOTENCY_KEY_SESSION')",
            name="ck_quota_bucket_type",
        ),
        sa.CheckConstraint(
            "NOT disabled OR bucket_type = 'QUESTION_GLOBAL'",
            name="ck_quota_disabled_question_global_only",
        ),
    )
    op.create_index("ix_quota_buckets_expires_at", "quota_buckets", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_quota_buckets_expires_at", table_name="quota_buckets")
    op.drop_table("quota_buckets")
    op.drop_index(
        "uq_idempotency_one_issued_per_session", table_name="idempotency_keys"
    )
    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_session_hmac", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_constraint(
        "uq_feedback_generation_result", "feedback", type_="unique"
    )
    op.drop_constraint("uq_feedback_request", "feedback", type_="unique")
    op.drop_constraint(
        "fk_feedback_generation_result_id", "feedback", type_="foreignkey"
    )
    op.drop_column("feedback", "generation_result_id")
    op.drop_column("generation_attempts", "usage_metadata")
    op.drop_index("ix_rag_requests_session_hmac", table_name="rag_requests")
    op.drop_column("rag_requests", "session_expires_at")
    op.drop_column("rag_requests", "session_hmac")
