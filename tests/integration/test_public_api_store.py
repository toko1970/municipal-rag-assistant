from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from src.persistence.database import get_engine
from src.persistence.models import IdempotencyKeyRow, QuotaBucketRow
from src.public_api_store import ApiStoreError, PostgresPublicApiStore


@pytest.mark.integration
def test_idempotency_registration_and_parallel_question_reservation_are_atomic():
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    now = datetime.now(timezone.utc)
    clock_values = [now]
    session_hmac = uuid4().hex + uuid4().hex
    key_hmac = uuid4().hex + uuid4().hex
    store = PostgresPublicApiStore(factory, clock=lambda: clock_values[0])
    session_expiry = now + timedelta(hours=12)

    try:
        first_registration = store.register_key(
            session_hmac=session_hmac,
            key_hmac=key_hmac,
            session_expires_at=session_expiry,
        )
        replay_registration = store.register_key(
            session_hmac=session_hmac,
            key_hmac=key_hmac,
            session_expires_at=session_expiry,
        )
        assert replay_registration == first_registration

        def reserve():
            return store.reserve_question(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                body_hash="d" * 64,
                session_expires_at=session_expiry,
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            registration_future = executor.submit(
                store.register_key,
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                session_expires_at=session_expiry,
            )
            reserve_futures = [executor.submit(reserve) for _ in range(7)]
            states = [future.result(timeout=20) for future in reserve_futures]
            concurrent_registration = registration_future.result(timeout=20)

        assert sum(state.newly_claimed for state in states) == 1
        assert {state.state for state in states} == {"IN_PROGRESS"}
        assert concurrent_registration == first_registration
        with factory() as session:
            key_count = session.scalar(
                select(QuotaBucketRow.reserved_count).where(
                    QuotaBucketRow.bucket_type == "IDEMPOTENCY_KEY_SESSION",
                    QuotaBucketRow.bucket_key == session_hmac,
                )
            )
            question_count = session.scalar(
                select(QuotaBucketRow.reserved_count).where(
                    QuotaBucketRow.bucket_type == "QUESTION_SESSION",
                    QuotaBucketRow.bucket_key == session_hmac,
                )
            )
            key_rows = session.scalar(
                select(IdempotencyKeyRow.id).where(
                    IdempotencyKeyRow.session_hmac == session_hmac
                )
            )
        assert key_count == 1
        assert question_count == 1
        assert key_rows is not None

        clock_values[0] = now + timedelta(seconds=151)
        interrupted = store.expire_stuck_request(
            session_hmac=session_hmac,
            key_hmac=key_hmac,
            max_age=timedelta(seconds=150),
        )
        assert interrupted is not None
        assert interrupted.state == "INTERRUPTED"
        assert (
            store.finish_request(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                request_id=None,
                state="COMPLETE",
            )
            == "INTERRUPTED"
        )

        with pytest.raises(ApiStoreError) as conflict:
            store.reserve_question(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                body_hash="e" * 64,
                session_expires_at=session_expiry,
            )
        assert conflict.value.status_code == 409
    finally:
        with factory() as session, session.begin():
            session.execute(
                delete(IdempotencyKeyRow).where(
                    IdempotencyKeyRow.session_hmac == session_hmac
                )
            )
            session.execute(
                delete(QuotaBucketRow).where(QuotaBucketRow.bucket_key == session_hmac)
            )
