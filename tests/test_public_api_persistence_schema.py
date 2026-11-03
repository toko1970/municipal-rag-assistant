from sqlalchemy import CheckConstraint, PrimaryKeyConstraint, UniqueConstraint

from src.persistence.models import (
    FeedbackRow,
    GenerationAttemptRow,
    IdempotencyKeyRow,
    QuotaBucketRow,
    RagRequestRow,
)


def test_idempotency_rows_store_only_scoped_hashes_and_expiring_request_state():
    columns = IdempotencyKeyRow.__table__.columns

    assert {"key_hmac", "session_hmac", "submit_by", "session_expires_at", "expires_at", "state", "body_hash", "request_id"} <= set(columns.keys())
    assert "raw_key" not in columns
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns}
        == {"session_hmac", "key_hmac"}
        for constraint in IdempotencyKeyRow.__table__.constraints
    )


def test_quota_rows_have_atomic_bucket_identity_and_expiry():
    columns = QuotaBucketRow.__table__.columns

    assert {"bucket_date", "bucket_type", "bucket_key", "reserved_count", "limit_count", "disabled", "expires_at"} <= set(columns.keys())
    assert any(
        isinstance(constraint, PrimaryKeyConstraint)
        and {column.name for column in constraint.columns}
        == {"bucket_date", "bucket_type", "bucket_key"}
        for constraint in QuotaBucketRow.__table__.constraints
    )
    assert any(isinstance(item, CheckConstraint) for item in QuotaBucketRow.__table__.constraints)


def test_requests_and_feedback_retain_session_ownership_and_one_feedback_per_request():
    assert {"session_hmac", "session_expires_at"} <= set(RagRequestRow.__table__.columns.keys())
    assert "generation_result_id" in FeedbackRow.__table__.columns
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"request_id"}
        for constraint in FeedbackRow.__table__.constraints
    )


def test_generation_attempt_persists_safe_metadata_for_idempotent_response_replay():
    assert "usage_metadata" in GenerationAttemptRow.__table__.columns
