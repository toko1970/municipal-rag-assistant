"""Bounded cleanup for expired anonymous idempotency and quota identifiers."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import delete, select, tuple_

from src.persistence.models import IdempotencyKeyRow, QuotaBucketRow


def cleanup_expired_state(
    session_factory,
    *,
    now: datetime | None = None,
    batch_size: int = 500,
) -> dict[str, int]:
    """Delete only expired HMAC key and quota rows, in repeatable batches."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    cutoff = now or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cutoff = cutoff.astimezone(timezone.utc)
    counts = {"idempotency_keys": 0, "quota_buckets": 0}

    while True:
        with session_factory() as session, session.begin():
            key_ids = (
                select(IdempotencyKeyRow.id)
                .where(IdempotencyKeyRow.expires_at <= cutoff)
                .order_by(IdempotencyKeyRow.expires_at, IdempotencyKeyRow.id)
                .limit(batch_size)
            )
            key_rows = session.execute(
                delete(IdempotencyKeyRow)
                .where(IdempotencyKeyRow.id.in_(key_ids))
                .returning(IdempotencyKeyRow.id)
            ).all()

            bucket_keys = (
                select(
                    QuotaBucketRow.bucket_date,
                    QuotaBucketRow.bucket_type,
                    QuotaBucketRow.bucket_key,
                )
                .where(QuotaBucketRow.expires_at <= cutoff)
                .order_by(
                    QuotaBucketRow.expires_at,
                    QuotaBucketRow.bucket_date,
                    QuotaBucketRow.bucket_type,
                    QuotaBucketRow.bucket_key,
                )
                .limit(batch_size)
            )
            bucket_rows = session.execute(
                delete(QuotaBucketRow)
                .where(
                    tuple_(
                        QuotaBucketRow.bucket_date,
                        QuotaBucketRow.bucket_type,
                        QuotaBucketRow.bucket_key,
                    ).in_(bucket_keys)
                )
                .returning(QuotaBucketRow.bucket_date)
            ).all()

        key_count = len(key_rows)
        bucket_count = len(bucket_rows)
        counts["idempotency_keys"] += key_count
        counts["quota_buckets"] += bucket_count
        if key_count == 0 and bucket_count == 0:
            return counts
