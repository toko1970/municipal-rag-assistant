from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.persistence.database import get_engine
from src.persistence.models import IdempotencyKeyRow, QuotaBucketRow
from src.public_api_cleanup import cleanup_expired_state


@pytest.mark.integration
def test_cleanup_removes_only_expired_hmac_and_quota_rows_in_batches():
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    now = datetime.now(timezone.utc)
    expired_session_hmac = uuid4().hex + uuid4().hex
    active_session_hmac = uuid4().hex + uuid4().hex
    expired_key_hmac = uuid4().hex + uuid4().hex
    active_key_hmac = uuid4().hex + uuid4().hex
    expired_day = date.today() - timedelta(days=3)
    active_day = date.today()
    with factory() as session, session.begin():
        session.add_all(
            [
                IdempotencyKeyRow(
                    id=uuid4(),
                    session_hmac=expired_session_hmac,
                    key_hmac=expired_key_hmac,
                    submit_by=now - timedelta(days=2),
                    session_expires_at=now - timedelta(days=2),
                    expires_at=now,
                    state="EXPIRED",
                ),
                IdempotencyKeyRow(
                    id=uuid4(),
                    session_hmac=active_session_hmac,
                    key_hmac=active_key_hmac,
                    submit_by=now + timedelta(minutes=2),
                    session_expires_at=now + timedelta(hours=1),
                    expires_at=now + timedelta(hours=1),
                    state="ISSUED",
                ),
                QuotaBucketRow(
                    bucket_date=expired_day,
                    bucket_type="IDEMPOTENCY_KEY_SESSION",
                    bucket_key=expired_session_hmac,
                    reserved_count=1,
                    limit_count=10,
                    disabled=False,
                    expires_at=now,
                ),
                QuotaBucketRow(
                    bucket_date=active_day,
                    bucket_type="IDEMPOTENCY_KEY_SESSION",
                    bucket_key=active_session_hmac,
                    reserved_count=1,
                    limit_count=10,
                    disabled=False,
                    expires_at=now + timedelta(hours=1),
                ),
            ]
        )

    try:
        removed = cleanup_expired_state(factory, now=now, batch_size=1)
        repeated = cleanup_expired_state(factory, now=now, batch_size=1)

        assert removed == {"idempotency_keys": 1, "quota_buckets": 1}
        assert repeated == {"idempotency_keys": 0, "quota_buckets": 0}
        with factory() as session:
            assert session.scalar(
                select(IdempotencyKeyRow.id).where(
                    IdempotencyKeyRow.key_hmac == active_key_hmac
                )
            ) is not None
            assert session.scalar(
                select(QuotaBucketRow.bucket_key).where(
                    QuotaBucketRow.bucket_key == active_session_hmac
                )
            ) == active_session_hmac
    finally:
        with factory() as session, session.begin():
            session.query(IdempotencyKeyRow).filter(
                IdempotencyKeyRow.session_hmac.in_(
                    [expired_session_hmac, active_session_hmac]
                )
            ).delete(synchronize_session=False)
            session.query(QuotaBucketRow).filter(
                QuotaBucketRow.bucket_key.in_(
                    [expired_session_hmac, active_session_hmac]
                )
            ).delete(synchronize_session=False)
