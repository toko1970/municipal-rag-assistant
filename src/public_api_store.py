"""PostgreSQL transactions for anonymous API ownership and quotas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.asset_store import VisualEvidenceAsset
from src.persistence.models import (
    ContentElementRow,
    DocumentRow,
    DocumentVersionRow,
    FeedbackRow,
    GenerationAttemptRow,
    GenerationResultRow,
    IdempotencyKeyRow,
    QuotaBucketRow,
    RagRequestRow,
    RetrievalResultRow,
    VisualAssetRow,
)


JST = ZoneInfo("Asia/Tokyo")
GLOBAL_BUCKET_KEY = "global"
QUESTION_SESSION_LIMIT = 5
QUESTION_GLOBAL_LIMIT = 50
FEEDBACK_SESSION_LIMIT = 10
FEEDBACK_GLOBAL_LIMIT = 200
KEY_SESSION_LIMIT = 10
KEY_GLOBAL_LIMIT = 200


class ApiStoreError(Exception):
    def __init__(
        self, code: str, status_code: int, message: str, *, retryable: bool = False
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class KeyRegistration:
    submit_by: datetime
    session_expires_at: datetime


@dataclass(frozen=True)
class KeyState:
    state: str
    request_id: UUID | None
    submit_by: datetime
    session_expires_at: datetime
    updated_at: datetime
    newly_claimed: bool = False


@dataclass(frozen=True)
class RequestSnapshot:
    result: dict[str, Any]
    status: str
    failure_code: str | None = None


def _now_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _bucket_expiry(bucket_day: date) -> datetime:
    return datetime.combine(bucket_day + timedelta(days=1), time.min, tzinfo=JST).astimezone(
        timezone.utc
    )


class PostgresPublicApiStore:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock

    def _lock_bucket(
        self,
        session: Session,
        *,
        bucket_day: date,
        bucket_type: str,
        bucket_key: str,
        limit_count: int,
        expires_at: datetime,
    ) -> QuotaBucketRow:
        insert = pg_insert(QuotaBucketRow).values(
            bucket_date=bucket_day,
            bucket_type=bucket_type,
            bucket_key=bucket_key,
            reserved_count=0,
            limit_count=limit_count,
            disabled=False,
            expires_at=expires_at,
        )
        session.execute(
            insert.on_conflict_do_nothing(
                index_elements=[
                    QuotaBucketRow.bucket_date,
                    QuotaBucketRow.bucket_type,
                    QuotaBucketRow.bucket_key,
                ]
            )
        )
        row = session.scalar(
            select(QuotaBucketRow)
            .where(
                QuotaBucketRow.bucket_date == bucket_day,
                QuotaBucketRow.bucket_type == bucket_type,
                QuotaBucketRow.bucket_key == bucket_key,
            )
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("quota bucket disappeared during reservation")
        return row

    def _key_issue_buckets(
        self, session: Session, session_hmac: str, bucket_day: date, expires_at: datetime
    ) -> tuple[QuotaBucketRow, QuotaBucketRow, QuotaBucketRow]:
        # Every code path takes locks in global-then-session order.
        question_global = self._lock_bucket(
            session,
            bucket_day=bucket_day,
            bucket_type="QUESTION_GLOBAL",
            bucket_key=GLOBAL_BUCKET_KEY,
            limit_count=QUESTION_GLOBAL_LIMIT,
            expires_at=_bucket_expiry(bucket_day),
        )
        key_global = self._lock_bucket(
            session,
            bucket_day=bucket_day,
            bucket_type="IDEMPOTENCY_KEY_GLOBAL",
            bucket_key=GLOBAL_BUCKET_KEY,
            limit_count=KEY_GLOBAL_LIMIT,
            expires_at=_bucket_expiry(bucket_day),
        )
        key_session = self._lock_bucket(
            session,
            bucket_day=bucket_day,
            bucket_type="IDEMPOTENCY_KEY_SESSION",
            bucket_key=session_hmac,
            limit_count=KEY_SESSION_LIMIT,
            expires_at=expires_at,
        )
        return question_global, key_global, key_session

    @staticmethod
    def _reserve(rows: tuple[QuotaBucketRow, ...], *, include_disabled: bool = False) -> None:
        for row in rows:
            if include_disabled and row.disabled:
                raise ApiStoreError(
                    "GLOBAL_QUESTION_DISABLED",
                    503,
                    "質問受付は一時停止しています。時間を置いて再度お試しください。",
                    retryable=True,
                )
            if row.reserved_count >= row.limit_count:
                prefix = {
                    "QUESTION_GLOBAL": "QUOTA_QUESTION_GLOBAL",
                    "QUESTION_SESSION": "QUOTA_QUESTION_SESSION",
                    "FEEDBACK_GLOBAL": "QUOTA_FEEDBACK_GLOBAL",
                    "FEEDBACK_SESSION": "QUOTA_FEEDBACK_SESSION",
                    "IDEMPOTENCY_KEY_GLOBAL": "QUOTA_KEY_GLOBAL",
                    "IDEMPOTENCY_KEY_SESSION": "QUOTA_KEY_SESSION",
                }[row.bucket_type]
                raise ApiStoreError(
                    prefix,
                    429,
                    "本日の利用上限に達しました。時間を置いて再度お試しください。",
                )
            row.reserved_count += 1

    def register_key(
        self,
        *,
        session_hmac: str,
        key_hmac: str,
        session_expires_at: datetime,
    ) -> KeyRegistration:
        now = _now_utc(self.clock())
        session_expiry = _now_utc(session_expires_at)
        if now >= session_expiry:
            raise ApiStoreError(
                "SESSION_INVALID", 410, "セッションの有効期限が切れました。ページを再読み込みしてください。"
            )
        bucket_day = now.astimezone(JST).date()
        expired = False
        registration: KeyRegistration | None = None
        with self.session_factory() as session, session.begin():
            question_global, key_global, key_session = self._key_issue_buckets(
                session, session_hmac, bucket_day, session_expiry
            )
            existing = session.scalar(
                select(IdempotencyKeyRow)
                .where(
                    IdempotencyKeyRow.session_hmac == session_hmac,
                    IdempotencyKeyRow.key_hmac == key_hmac,
                )
                .with_for_update()
            )
            if existing is not None:
                if now >= existing.expires_at or existing.state == "EXPIRED":
                    existing.state = "EXPIRED"
                    existing.updated_at = now
                    expired = True
                elif existing.state == "ISSUED" and now >= existing.submit_by:
                    existing.state = "EXPIRED"
                    existing.updated_at = now
                    expired = True
                else:
                    registration = KeyRegistration(
                        existing.submit_by, existing.session_expires_at
                    )
            else:
                active = session.scalar(
                    select(IdempotencyKeyRow)
                    .where(
                        IdempotencyKeyRow.session_hmac == session_hmac,
                        IdempotencyKeyRow.state == "ISSUED",
                    )
                    .with_for_update()
                )
                if active is not None and now >= active.submit_by:
                    active.state = "EXPIRED"
                    active.updated_at = now
                    active = None
                if active is not None:
                    raise ApiStoreError(
                        "IDEMPOTENCY_SLOT_BUSY",
                        409,
                        "前の質問送信がまだ確定していません。現在の送信を確認してください。",
                    )
                if question_global.disabled:
                    raise ApiStoreError(
                        "GLOBAL_QUESTION_DISABLED",
                        503,
                        "質問受付は一時停止しています。時間を置いて再度お試しください。",
                        retryable=True,
                    )
                self._reserve((key_global, key_session))
                submit_by = min(now + timedelta(minutes=5), session_expiry)
                row = IdempotencyKeyRow(
                    id=uuid4(),
                    key_hmac=key_hmac,
                    session_hmac=session_hmac,
                    submit_by=submit_by,
                    session_expires_at=session_expiry,
                    expires_at=session_expiry,
                    state="ISSUED",
                )
                session.add(row)
                registration = KeyRegistration(submit_by, session_expiry)
        if expired:
            raise ApiStoreError(
                "IDEMPOTENCY_KEY_EXPIRED", 410, "質問送信の有効期限が切れました。新しい質問を開始してください。"
            )
        if registration is None:
            raise RuntimeError("idempotency key registration returned no outcome")
        return registration

    def reserve_question(
        self,
        *,
        session_hmac: str,
        key_hmac: str,
        body_hash: str,
        session_expires_at: datetime,
    ) -> KeyState:
        now = _now_utc(self.clock())
        bucket_day = now.astimezone(JST).date()
        expired = False
        outcome: KeyState | None = None
        with self.session_factory() as session, session.begin():
            # Registration also locks QUESTION_GLOBAL first. Taking this gate
            # before the key row prevents an issue-vs-submit lock inversion.
            global_bucket = self._lock_bucket(
                session,
                bucket_day=bucket_day,
                bucket_type="QUESTION_GLOBAL",
                bucket_key=GLOBAL_BUCKET_KEY,
                limit_count=QUESTION_GLOBAL_LIMIT,
                expires_at=_bucket_expiry(bucket_day),
            )
            session_bucket = self._lock_bucket(
                session,
                bucket_day=bucket_day,
                bucket_type="QUESTION_SESSION",
                bucket_key=session_hmac,
                limit_count=QUESTION_SESSION_LIMIT,
                expires_at=_now_utc(session_expires_at),
            )
            key_row = session.scalar(
                select(IdempotencyKeyRow)
                .where(
                    IdempotencyKeyRow.session_hmac == session_hmac,
                    IdempotencyKeyRow.key_hmac == key_hmac,
                )
                .with_for_update()
            )
            if key_row is None:
                raise ApiStoreError(
                    "IDEMPOTENCY_KEY_UNKNOWN", 404, "質問送信キーが見つかりません。"
                )
            if now >= key_row.expires_at or key_row.state == "EXPIRED":
                key_row.state = "EXPIRED"
                key_row.updated_at = now
                expired = True
            elif key_row.state == "ISSUED" and now >= key_row.submit_by:
                key_row.state = "EXPIRED"
                key_row.updated_at = now
                expired = True
            elif key_row.state != "ISSUED":
                if key_row.body_hash != body_hash:
                    raise ApiStoreError(
                        "IDEMPOTENCY_BODY_CONFLICT",
                        409,
                        "同じ送信キーに異なる質問は指定できません。",
                    )
                outcome = KeyState(
                    key_row.state,
                    key_row.request_id,
                    key_row.submit_by,
                    key_row.session_expires_at,
                    key_row.updated_at,
                )
            else:
                if global_bucket.disabled:
                    raise ApiStoreError(
                        "GLOBAL_QUESTION_DISABLED",
                        503,
                        "質問受付は一時停止しています。時間を置いて再度お試しください。",
                        retryable=True,
                    )
                self._reserve((global_bucket, session_bucket))
                key_row.body_hash = body_hash
                key_row.state = "IN_PROGRESS"
                key_row.updated_at = now
                outcome = KeyState(
                    key_row.state,
                    key_row.request_id,
                    key_row.submit_by,
                    key_row.session_expires_at,
                    key_row.updated_at,
                    True,
                )
        if expired:
            raise ApiStoreError(
                "IDEMPOTENCY_KEY_EXPIRED", 410, "質問送信キーの有効期限が切れました。"
            )
        if outcome is None:
            raise RuntimeError("question reservation returned no outcome")
        return outcome

    def finish_request(
        self,
        *,
        session_hmac: str,
        key_hmac: str,
        request_id: UUID | None,
        state: str,
    ) -> str | None:
        if state not in {"COMPLETE", "FAILED"}:
            raise ValueError("invalid final idempotency state")
        now = _now_utc(self.clock())
        with self.session_factory() as session, session.begin():
            row = session.scalar(
                select(IdempotencyKeyRow)
                .where(
                    IdempotencyKeyRow.session_hmac == session_hmac,
                    IdempotencyKeyRow.key_hmac == key_hmac,
                )
                .with_for_update()
            )
            if row is None:
                return None
            if row.state != "IN_PROGRESS":
                return row.state
            row.request_id = request_id
            row.state = state
            row.updated_at = now
            return row.state

    def expire_stuck_request(
        self, *, session_hmac: str, key_hmac: str, max_age: timedelta
    ) -> KeyState | None:
        now = _now_utc(self.clock())
        with self.session_factory() as session, session.begin():
            row = session.scalar(
                select(IdempotencyKeyRow)
                .where(
                    IdempotencyKeyRow.session_hmac == session_hmac,
                    IdempotencyKeyRow.key_hmac == key_hmac,
                )
                .with_for_update()
            )
            if row is None:
                return None
            if row.state == "IN_PROGRESS" and row.updated_at <= now - max_age:
                row.state = "INTERRUPTED"
                row.updated_at = now
            return KeyState(
                row.state,
                row.request_id,
                row.submit_by,
                row.session_expires_at,
                row.updated_at,
            )

    def lookup_key(self, *, session_hmac: str, key_hmac: str) -> KeyState | None:
        now = _now_utc(self.clock())
        expired = False
        result = None
        with self.session_factory() as session, session.begin():
            row = session.scalar(
                select(IdempotencyKeyRow).where(
                    IdempotencyKeyRow.session_hmac == session_hmac,
                    IdempotencyKeyRow.key_hmac == key_hmac,
                ).with_for_update()
            )
            if row is None:
                return None
            if (
                now >= row.expires_at
                or row.state == "EXPIRED"
                or (row.state == "ISSUED" and now >= row.submit_by)
            ):
                row.state = "EXPIRED"
                row.updated_at = now
                expired = True
            elif row.state == "ISSUED":
                return None
            else:
                result = KeyState(
                    row.state,
                    row.request_id,
                    row.submit_by,
                    row.session_expires_at,
                    row.updated_at,
                )
        if expired:
            raise ApiStoreError(
                "IDEMPOTENCY_KEY_EXPIRED", 410, "質問送信キーの有効期限が切れました。"
            )
        return result

    def request_snapshot(
        self, *, request_id: UUID, session_hmac: str
    ) -> RequestSnapshot | None:
        with self.session_factory() as session:
            request = session.get(RagRequestRow, request_id)
            if (
                request is None
                or request.session_hmac != session_hmac
                or request.session_expires_at is None
                or _now_utc(self.clock()) >= request.session_expires_at
            ):
                return None
            generation = session.scalar(
                select(GenerationResultRow).where(
                    GenerationResultRow.request_id == request_id
                )
            )
            attempt = session.scalar(
                select(GenerationAttemptRow)
                .where(GenerationAttemptRow.request_id == request_id)
                .order_by(GenerationAttemptRow.created_at.desc())
            )
            retrieval_rows = session.execute(
                select(RetrievalResultRow, ContentElementRow, DocumentVersionRow, DocumentRow)
                .join(
                    ContentElementRow,
                    RetrievalResultRow.content_element_id == ContentElementRow.id,
                )
                .join(
                    DocumentVersionRow,
                    ContentElementRow.document_version_id == DocumentVersionRow.id,
                )
                .join(DocumentRow, DocumentVersionRow.document_id == DocumentRow.id)
                .where(RetrievalResultRow.request_id == request_id)
                .order_by(RetrievalResultRow.rank)
            ).all()
            asset_rows = {}
            element_ids = [element.id for _retrieval, element, _version, _document in retrieval_rows]
            if element_ids:
                assets = session.scalars(
                    select(VisualAssetRow)
                    .where(VisualAssetRow.content_element_id.in_(element_ids))
                    .order_by(VisualAssetRow.page_number, VisualAssetRow.id)
                ).all()
                for asset in assets:
                    asset_rows.setdefault(asset.content_element_id, asset)

            answer = generation.display_text if generation else None
            label = generation.final_label if generation else None
            status = generation.status if generation else "GENERATION_FAILED"
            references: list[dict[str, Any]] = []
            for retrieval, element, version, document in retrieval_rows:
                metadata = dict(element.structured_data or {})
                ref: dict[str, Any] = {
                    "reference_id": str(element.id),
                    "element_id": str(element.id),
                    "document_id": str(metadata.get("document_key") or document.id),
                    "document_name": document.title,
                    "heading": element.heading,
                    "content": element.content_text,
                    "chunk_id": metadata.get("ordinal", retrieval.rank),
                    "score": round(retrieval.score, 4),
                    "source": metadata.get("source_path") or metadata.get("source", ""),
                    "version_id": str(version.id),
                    "page_number": element.page_number,
                }
                for key in (
                    "effective_date",
                    "version",
                    "document_role",
                    "is_primary",
                    "content_hash",
                ):
                    if key in metadata:
                        ref[key] = metadata[key]
                asset = asset_rows.get(element.id)
                if asset is not None:
                    image_url = (
                        f"/api/requests/{request_id}/references/{element.id}/image"
                    )
                    image_alt = f"{document.title} p.{asset.page_number}の図表"
                    ref["image_url"] = image_url
                    ref["image_alt"] = image_alt
                    ref["visual_asset"] = {
                        "url": image_url,
                        "mime_type": asset.mime_type,
                        "page_number": asset.page_number,
                        "alt": image_alt,
                    }
                references.append(ref)
            usage = (
                dict(attempt.usage_metadata)
                if attempt and attempt.usage_metadata
                else {
                    "provider": attempt.provider if attempt else "",
                    "model": attempt.model if attempt else "",
                    "input_tokens": attempt.input_tokens if attempt else 0,
                    "output_tokens": attempt.output_tokens if attempt else 0,
                    "total_tokens": (attempt.input_tokens + attempt.output_tokens)
                    if attempt
                    else 0,
                    "request_id": "",
                    "finish_reason": None,
                }
            )
            result = {
                "request_id": str(request_id),
                "answer": answer
                or "回答の準備に失敗しました。時間を置いて再実行してください。",
                "answer_label": label,
                "answer_status": status,
                "degraded": status != "SUCCESS",
                "references": references,
                "generation": usage,
            }
            return RequestSnapshot(
                result,
                status,
                self._failure_code(status, attempt.error_summary if attempt else None),
            )

    @staticmethod
    def _failure_code(status: str, error_summary: str | None) -> str | None:
        if status in {"SUCCESS", "GENERATION_INCOMPLETE"}:
            return None
        error_name = (error_summary or "").lower()
        if any(token in error_name for token in ("timeout", "deadline")):
            return "PROVIDER_TIMEOUT"
        if any(token in error_name for token in ("resourceexhausted", "ratelimit", "quota")):
            return "PROVIDER_LIMITED"
        if status == "GENERATION_FAILED" or status == "GENERATION_INCOMPLETE":
            return "PROVIDER_UNAVAILABLE"
        if status.endswith("_FAILED"):
            return "DEPENDENCY_UNAVAILABLE"
        return "PROVIDER_UNAVAILABLE"

    def save_feedback(
        self,
        *,
        request_id: UUID,
        session_hmac: str,
        value: str,
        comment: str,
    ) -> None:
        now = _now_utc(self.clock())
        bucket_day = now.astimezone(JST).date()
        with self.session_factory() as session, session.begin():
            request = session.scalar(
                select(RagRequestRow)
                .where(RagRequestRow.id == request_id)
                .with_for_update()
            )
            if (
                request is None
                or request.session_hmac != session_hmac
                or request.session_expires_at is None
                or now >= request.session_expires_at
            ):
                raise ApiStoreError(
                    "REQUEST_NOT_FOUND", 404, "対象の回答が見つかりません。"
                )
            generation = session.scalar(
                select(GenerationResultRow).where(
                    GenerationResultRow.request_id == request_id
                )
            )
            if generation is None:
                raise ApiStoreError(
                    "REQUEST_NOT_FOUND", 404, "対象の回答が見つかりません。"
                )
            global_bucket = self._lock_bucket(
                session,
                bucket_day=bucket_day,
                bucket_type="FEEDBACK_GLOBAL",
                bucket_key=GLOBAL_BUCKET_KEY,
                limit_count=FEEDBACK_GLOBAL_LIMIT,
                expires_at=_bucket_expiry(bucket_day),
            )
            session_bucket = self._lock_bucket(
                session,
                bucket_day=bucket_day,
                bucket_type="FEEDBACK_SESSION",
                bucket_key=session_hmac,
                limit_count=FEEDBACK_SESSION_LIMIT,
                expires_at=request.session_expires_at,
            )
            self._reserve((global_bucket, session_bucket))
            existing = session.scalar(
                select(FeedbackRow).where(FeedbackRow.request_id == request_id)
            )
            if existing is None:
                session.add(
                    FeedbackRow(
                        id=uuid4(),
                        request_id=request_id,
                        generation_result_id=generation.id,
                        value=value,
                        comment=comment,
                    )
                )
            else:
                existing.value = value
                existing.comment = comment
                existing.generation_result_id = generation.id

    def authorized_asset(
        self, *, request_id: UUID, reference_id: UUID, session_hmac: str
    ) -> VisualEvidenceAsset | None:
        now = _now_utc(self.clock())
        with self.session_factory() as session:
            request = session.get(RagRequestRow, request_id)
            if (
                request is None
                or request.session_hmac != session_hmac
                or request.session_expires_at is None
                or now >= request.session_expires_at
            ):
                return None
            retrieved = session.scalar(
                select(RetrievalResultRow.id).where(
                    RetrievalResultRow.request_id == request_id,
                    RetrievalResultRow.content_element_id == reference_id,
                )
            )
            if retrieved is None:
                return None
            asset = session.scalar(
                select(VisualAssetRow)
                .where(VisualAssetRow.content_element_id == reference_id)
                .order_by(VisualAssetRow.page_number, VisualAssetRow.id)
            )
            if asset is None:
                return None
            return VisualEvidenceAsset(
                element_id=asset.content_element_id,
                storage_uri=asset.storage_uri,
                mime_type=asset.mime_type,
                page_number=asset.page_number,
                sha256=asset.sha256,
                bbox=dict(asset.bbox) if asset.bbox else None,
            )
