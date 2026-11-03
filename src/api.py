"""FastAPI composition root for the same-origin public RAG interface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Callable, Literal
import unicodedata
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StrictStr, field_validator
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool
import yaml

from config import (
    CANONICAL_ORIGIN,
    DATABASE_URL,
    QDRANT_API_KEY,
    QDRANT_URL,
    SESSION_CURRENT_KEY_ID,
    SESSION_SIGNING_KEYS_JSON,
)
from src.asset_backend import get_asset_reader
from src.public_api_store import (
    ApiStoreError,
    KeyState,
    PostgresPublicApiStore,
    RequestSnapshot,
)
from src.request_context import (
    bind_public_request_context,
    current_public_request_context,
    reset_public_request_context,
)
from src.session_security import (
    SessionTokenCodec,
    SessionTokenError,
    SessionTokenExpired,
)


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
SESSION_COOKIE_NAME = "rag_session"
MAX_JSON_BODY_BYTES = 16 * 1024
MAX_QUERY_SECONDS = 120
INTERRUPTION_GRACE_SECONDS = 30
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
IMAGE_MIME_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}


class ApiProblem(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


class QuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question: StrictStr

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("QUESTION_EMPTY")
        if len(value) > 1000:
            raise ValueError("QUESTION_TOO_LONG")
        return value


class FeedbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: Literal["採用した", "修正して採用した", "採用しなかった"]
    comment: StrictStr

    @field_validator("comment", mode="before")
    @classmethod
    def normalize_comment(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = unicodedata.normalize(
            "NFC", "".join(character for character in value if unicodedata.category(character) != "Cc")
        )
        if len(normalized) > 2000:
            raise ValueError("FEEDBACK_TOO_LONG")
        return normalized


@dataclass(frozen=True)
class ApiDependencies:
    session_codec: SessionTokenCodec | None = None
    store: Any | None = None
    question_runner: Callable[[str], dict[str, Any]] | None = None
    readiness_probe: Callable[[], None] | None = None
    asset_reader: Any | None = None
    canonical_origin: str | None = None
    frontend_dist: Path | None = None


def _load_session_codec() -> SessionTokenCodec:
    try:
        raw_keys = json.loads(SESSION_SIGNING_KEYS_JSON)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApiProblem(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "セッション設定を読み込めません。時間を置いて再度お試しください。",
            retryable=True,
        ) from exc
    if not isinstance(raw_keys, dict) or not all(
        isinstance(key_id, str) and isinstance(secret, str)
        for key_id, secret in raw_keys.items()
    ):
        raise ApiProblem(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "セッション設定を読み込めません。時間を置いて再度お試しください。",
            retryable=True,
        )
    try:
        return SessionTokenCodec(
            signing_keys={key_id: secret.encode("utf-8") for key_id, secret in raw_keys.items()},
            current_key_id=SESSION_CURRENT_KEY_ID,
        )
    except ValueError as exc:
        raise ApiProblem(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "セッション設定を読み込めません。時間を置いて再度お試しください。",
            retryable=True,
        ) from exc


def _default_question_runner(question: str) -> dict[str, Any]:
    from src.rag_chain import generate_answer

    return generate_answer(question)


def _default_readiness_probe() -> None:
    url = make_url(DATABASE_URL)
    connect_args: dict[str, Any] = {"connect_timeout": 1}
    if url.get_backend_name() == "postgresql":
        connect_args["options"] = "-c statement_timeout=1000"
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
    from qdrant_client import QdrantClient

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=1)
    try:
        client.get_collections()
    finally:
        client.close()


def _api_error_body(code: str, message: str, retryable: bool) -> dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "retryable": retryable}
    }


def _store_problem(error: ApiStoreError) -> ApiProblem:
    return ApiProblem(
        error.status_code, error.code, error.message, retryable=error.retryable
    )


def _require_session(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise ApiProblem(401, "SESSION_REQUIRED", "ページを再読み込みしてからお試しください。")
    try:
        return _session_codec(request).verify(token)
    except SessionTokenExpired as exc:
        raise ApiProblem(
            410, "SESSION_INVALID", "セッションの有効期限が切れました。ページを再読み込みしてください。"
        ) from exc
    except SessionTokenError as exc:
        raise ApiProblem(401, "SESSION_INVALID", "セッションを確認できません。ページを再読み込みしてください。") from exc


def _require_same_origin_session(request: Request):
    claims = _require_session(request)
    canonical_origin = request.app.state.canonical_origin
    if not canonical_origin:
        raise ApiProblem(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "APIの公開設定が完了していません。時間を置いて再度お試しください。",
            retryable=True,
        )
    if request.headers.get("origin") != canonical_origin:
        raise ApiProblem(403, "ORIGIN_REJECTED", "この操作を受け付けられません。")
    if request.headers.get("sec-fetch-site") != "same-origin":
        raise ApiProblem(403, "ORIGIN_REJECTED", "この操作を受け付けられません。")
    return claims


def _session_codec(request: Request) -> SessionTokenCodec:
    codec = request.app.state.session_codec
    if codec is None:
        codec = _load_session_codec()
        request.app.state.session_codec = codec
    return codec


def _validate_idempotency_key(value: str, request: Request) -> str:
    if not IDEMPOTENCY_KEY_RE.fullmatch(value):
        raise ApiProblem(
            422,
            "IDEMPOTENCY_KEY_INVALID",
            "質問送信キーが不正です。新しい質問を開始してください。",
        )
    return value


def _body_hash(question: str) -> str:
    encoded = json.dumps(
        {"question": question}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _query_problem(exc: Exception) -> ApiProblem:
    name = type(exc).__name__.lower()
    module = type(exc).__module__
    if "timeout" in name or "deadline" in name:
        return ApiProblem(
            503,
            "PROVIDER_TIMEOUT",
            "回答の処理が時間内に完了しませんでした。新しい質問として再度お試しください。",
            retryable=False,
        )
    if "resourceexhausted" in name or "ratelimit" in name or "quota" in name:
        return ApiProblem(
            503,
            "PROVIDER_LIMITED",
            "回答サービスの利用上限に達しました。時間を置いて再度お試しください。",
            retryable=True,
        )
    if isinstance(exc, SQLAlchemyError) or module.startswith("qdrant_client"):
        return ApiProblem(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "検索サービスに接続できません。時間を置いて再度お試しください。",
            retryable=True,
        )
    if module.startswith(("google.api_core", "google.generativeai")) or any(
        term in name for term in ("resourceexhausted", "serviceunavailable", "apiconnection")
    ):
        return ApiProblem(
            503,
            "PROVIDER_UNAVAILABLE",
            "回答サービスを一時的に利用できません。新しい質問として再度お試しください。",
            retryable=False,
        )
    return ApiProblem(
        503,
        "INTERNAL_ERROR",
        "回答を作成できませんでした。時間を置いて再度お試しください。",
        retryable=True,
    )


def _failure_problem(snapshot: RequestSnapshot | None, state: KeyState) -> ApiProblem:
    if state.state == "INTERRUPTED":
        return ApiProblem(
            503,
            "PROCESS_INTERRUPTED",
            "回答処理が中断されました。同じ質問送信キーでは再実行されません。新しい質問としてお試しください。",
            retryable=False,
        )
    code = snapshot.failure_code if snapshot else None
    if code == "PROVIDER_TIMEOUT":
        return ApiProblem(
            503,
            code,
            "回答の処理が時間内に完了しませんでした。新しい質問として再度お試しください。",
            retryable=False,
        )
    if code == "PROVIDER_LIMITED":
        return ApiProblem(
            503,
            code,
            "回答サービスの利用上限に達しました。時間を置いて再度お試しください。",
            retryable=False,
        )
    if code == "DEPENDENCY_UNAVAILABLE":
        return ApiProblem(
            503,
            code,
            "検索サービスに接続できません。時間を置いて再度お試しください。",
            retryable=False,
        )
    return ApiProblem(
        503,
        code or "PROVIDER_UNAVAILABLE",
        "回答サービスを一時的に利用できません。新しい質問として再度お試しください。",
        retryable=False,
    )


def _serialize_result(raw_result: dict[str, Any]) -> dict[str, Any]:
    request_id = str(raw_result.get("request_id") or "")
    references = []
    for reference in raw_result.get("references", []):
        if not isinstance(reference, dict):
            continue
        normalized = {key: value for key, value in reference.items() if key != "visual_asset"}
        reference_id = reference.get("reference_id") or reference.get("element_id")
        asset = reference.get("visual_asset")
        if asset and isinstance(asset, dict) and request_id and reference_id:
            try:
                reference_uuid = UUID(str(reference_id))
            except ValueError:
                reference_uuid = None
            if reference_uuid is not None:
                image_url = f"/api/requests/{request_id}/references/{reference_uuid}/image"
                page_number = asset.get("page_number")
                document_name = str(reference.get("document_name") or "根拠資料")
                alt = f"{document_name} p.{page_number}の図表" if page_number else f"{document_name}の図表"
                normalized["reference_id"] = str(reference_uuid)
                normalized["image_url"] = image_url
                normalized["image_alt"] = alt
                normalized["visual_asset"] = {
                    "url": image_url,
                    "mime_type": asset.get("mime_type"),
                    "page_number": page_number,
                    "alt": alt,
                }
        references.append(normalized)
    payload = {
        "request_id": request_id,
        "answer": str(raw_result.get("answer") or ""),
        "answer_label": raw_result.get("answer_label"),
        "answer_status": str(raw_result.get("answer_status") or "UNKNOWN"),
        "degraded": bool(raw_result.get("degraded", False)),
        "references": references,
        "generation": raw_result.get("generation") or {},
    }
    for key in ("classification", "guidance", "classification_decision_version"):
        if key in raw_result:
            payload[key] = raw_result[key]
    return payload


class RequestBoundaryMiddleware:
    def __init__(self, app, *, max_body_bytes: int = MAX_JSON_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        needs_json = path == "/api/requests" or path.endswith("/feedback")
        if needs_json:
            headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
            content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                response = JSONResponse(
                    _api_error_body(
                        "CONTENT_TYPE_UNSUPPORTED",
                        "Content-Typeにapplication/jsonを指定してください。",
                        False,
                    ),
                    status_code=415,
                )
                await response(scope, receive, send)
                return
            content_length = headers.get("content-length")
            if content_length and content_length.isdecimal() and int(content_length) > self.max_body_bytes:
                response = JSONResponse(
                    _api_error_body("BODY_TOO_LARGE", "リクエストが大きすぎます。", False),
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            total = 0

            async def limited_receive():
                nonlocal total
                message = await receive()
                if message["type"] == "http.request":
                    total += len(message.get("body", b""))
                    if total > self.max_body_bytes:
                        raise _BodyTooLarge
                return message

            try:
                await self.app(scope, limited_receive, send)
            except _BodyTooLarge:
                response = JSONResponse(
                    _api_error_body("BODY_TOO_LARGE", "リクエストが大きすぎます。", False),
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            return
        await self.app(scope, receive, send)


class _BodyTooLarge(Exception):
    pass


def create_app(
    *,
    session_codec: SessionTokenCodec | None = None,
    store: Any | None = None,
    question_runner: Callable[[str], dict[str, Any]] | None = None,
    readiness_probe: Callable[[], None] | None = None,
    asset_reader: Any | None = None,
    canonical_origin: str | None = None,
    frontend_dist: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Municipal RAG Demo API",
        version="1.0.0",
        openapi_url="/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.state.session_codec = session_codec
    app.state.store = store or PostgresPublicApiStore(_session_factory())
    app.state.question_runner = question_runner or _default_question_runner
    app.state.readiness_probe = readiness_probe or _default_readiness_probe
    app.state.asset_reader = asset_reader
    app.state.canonical_origin = (
        canonical_origin if canonical_origin is not None else CANONICAL_ORIGIN
    )
    app.state.frontend_dist = frontend_dist or BASE_DIR / "frontend" / "dist"
    spec_path = BASE_DIR / "design" / "schemas" / "public-api-v1.openapi.yaml"
    app.state.openapi_spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    app.add_middleware(RequestBoundaryMiddleware)

    def custom_openapi():
        return app.state.openapi_spec

    app.openapi = custom_openapi

    @app.exception_handler(ApiProblem)
    async def handle_api_problem(_request: Request, exc: ApiProblem):
        return JSONResponse(
            _api_error_body(exc.code, exc.message, exc.retryable),
            status_code=exc.status_code,
        )

    @app.exception_handler(ApiStoreError)
    async def handle_store_problem(_request: Request, exc: ApiStoreError):
        problem = _store_problem(exc)
        return JSONResponse(
            _api_error_body(problem.code, problem.message, problem.retryable),
            status_code=problem.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        error_codes = [
            str(error.get("ctx", {}).get("error", "")) for error in errors
        ]
        if "QUESTION_TOO_LONG" in error_codes:
            problem = ApiProblem(422, "QUESTION_TOO_LONG", "質問は1,000文字以内で入力してください。")
        elif "QUESTION_EMPTY" in error_codes:
            problem = ApiProblem(422, "QUESTION_EMPTY", "質問を入力してください。")
        elif "FEEDBACK_TOO_LONG" in error_codes:
            problem = ApiProblem(422, "FEEDBACK_TOO_LONG", "コメントは2,000文字以内で入力してください。")
        elif request.url.path.endswith("/feedback") and any(
            error.get("loc") == ("body", "value") for error in errors
        ):
            problem = ApiProblem(
                422,
                "FEEDBACK_INVALID",
                "フィードバックの選択肢を確認してください。",
            )
        elif request.url.path in {"/api/requests", "/api/requests/by-idempotency-key", "/api/idempotency-keys"} and any(
            error.get("loc") == ("header", "Idempotency-Key") for error in errors
        ):
            problem = ApiProblem(
                422,
                "IDEMPOTENCY_KEY_INVALID",
                "質問送信キーが不正です。新しい質問を開始してください。",
            )
        else:
            problem = ApiProblem(422, "INVALID_REQUEST", "入力内容を確認してください。")
        return JSONResponse(
            _api_error_body(problem.code, problem.message, problem.retryable),
            status_code=problem.status_code,
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(_request: Request, _exc: SQLAlchemyError):
        return JSONResponse(
            _api_error_body(
                "DEPENDENCY_UNAVAILABLE",
                "保存サービスに接続できません。時間を置いて再度お試しください。",
                True,
            ),
            status_code=503,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception):
        logger.warning("api_request_failed error_type=%s", type(exc).__name__)
        return JSONResponse(
            _api_error_body(
                "INTERNAL_ERROR",
                "処理を完了できませんでした。時間を置いて再度お試しください。",
                True,
            ),
            status_code=500,
        )

    @app.get("/api/health/live", response_model=None)
    def health_live():
        return {"status": "ok"}

    @app.get("/api/health/ready", response_model=None)
    def health_ready(request: Request):
        try:
            request.app.state.readiness_probe()
        except Exception:
            raise ApiProblem(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "検索サービスを一時的に利用できません。",
                retryable=True,
            ) from None
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def spa_root(request: Request):
        frontend = request.app.state.frontend_dist
        index_path = frontend / "index.html"
        if index_path.is_file():
            response: Response = FileResponse(index_path, media_type="text/html")
        else:
            response = HTMLResponse(
                "<!doctype html><html lang='ja'><meta charset='utf-8'>"
                "<title>RAG Portfolio</title><body><main>UI build is not available.</main></body></html>"
            )
        response.headers["Cache-Control"] = "no-store"
        token = request.cookies.get(SESSION_COOKIE_NAME)
        codec = _session_codec(request)
        try:
            if token:
                codec.verify(token)
                return response
        except SessionTokenError:
            pass
        signed_cookie, claims = codec.issue()
        response.set_cookie(
            SESSION_COOKIE_NAME,
            signed_cookie,
            max_age=max(1, claims.expires_at - int(codec.clock())),
            expires=datetime.fromtimestamp(claims.expires_at, tz=timezone.utc),
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/api/idempotency-keys", response_model=None)
    def issue_idempotency_key(
        request: Request,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        claims=Depends(_require_same_origin_session),
    ):
        key = _validate_idempotency_key(idempotency_key, request)
        codec = _session_codec(request)
        try:
            registration = request.app.state.store.register_key(
                session_hmac=codec.session_hmac(claims),
                key_hmac=codec.key_hmac(claims, key),
                session_expires_at=datetime.fromtimestamp(
                    claims.expires_at, tz=timezone.utc
                ),
            )
        except ApiStoreError as exc:
            raise _store_problem(exc) from exc
        return {
            "submit_by": registration.submit_by.isoformat(),
            "session_expires_at": registration.session_expires_at.isoformat(),
        }

    @app.post("/api/requests", response_model=None)
    def create_request(
        request: Request,
        body: QuestionBody,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        claims=Depends(_require_same_origin_session),
    ):
        key = _validate_idempotency_key(idempotency_key, request)
        codec = _session_codec(request)
        session_hmac = codec.session_hmac(claims)
        key_hmac = codec.key_hmac(claims, key)
        try:
            key_state = request.app.state.store.reserve_question(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                body_hash=_body_hash(body.question),
                session_expires_at=datetime.fromtimestamp(
                    claims.expires_at, tz=timezone.utc
                ),
            )
        except ApiStoreError as exc:
            raise _store_problem(exc) from exc
        if key_state.state == "IN_PROGRESS" and not key_state.newly_claimed:
            key_state = request.app.state.store.expire_stuck_request(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                max_age=timedelta(
                    seconds=MAX_QUERY_SECONDS + INTERRUPTION_GRACE_SECONDS
                ),
            )
            if key_state is not None and key_state.state == "IN_PROGRESS":
                return JSONResponse(
                    {"status": "processing"},
                    status_code=202,
                    headers={"Retry-After": "3"},
                )
        if key_state.state in {"COMPLETE", "FAILED", "INTERRUPTED"}:
            snapshot = (
                request.app.state.store.request_snapshot(
                    request_id=key_state.request_id, session_hmac=session_hmac
                )
                if key_state.request_id
                else None
            )
            if key_state.state != "COMPLETE":
                raise _failure_problem(snapshot, key_state)
            if snapshot is not None:
                return snapshot.result

        token = bind_public_request_context(
            session_hmac, datetime.fromtimestamp(claims.expires_at, tz=timezone.utc)
        )
        started_at = time.monotonic()
        try:
            raw_result = request.app.state.question_runner(body.question)
            request_id_value = raw_result.get("request_id")
            request_id = UUID(str(request_id_value)) if request_id_value else None
            if request_id is None:
                raise RuntimeError("query entry point did not return a request ID")
            finished_state = request.app.state.store.finish_request(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                request_id=request_id,
                state="COMPLETE",
            )
            if finished_state is None:
                raise ApiProblem(
                    503,
                    "DEPENDENCY_UNAVAILABLE",
                    "質問の状態を保存できませんでした。時間を置いて再度お試しください。",
                    retryable=True,
                )
            if finished_state != "COMPLETE":
                terminal_state = KeyState(
                    finished_state,
                    request_id,
                    key_state.submit_by,
                    key_state.session_expires_at,
                    key_state.updated_at,
                )
                snapshot = request.app.state.store.request_snapshot(
                    request_id=request_id, session_hmac=session_hmac
                )
                raise _failure_problem(snapshot, terminal_state)
            snapshot = request.app.state.store.request_snapshot(
                request_id=request_id, session_hmac=session_hmac
            )
            return snapshot.result if snapshot is not None else _serialize_result(raw_result)
        except ApiStoreError as exc:
            raise _store_problem(exc) from exc
        except ApiProblem:
            raise
        except Exception as exc:
            context = current_public_request_context()
            request_id = context.request_id if context else None
            if request_id is None:
                try:
                    fallback_id = locals().get("raw_result", {}).get("request_id")
                    request_id = UUID(str(fallback_id)) if fallback_id else None
                except (ValueError, TypeError):
                    request_id = None
            terminal_state = None
            try:
                terminal_state = request.app.state.store.finish_request(
                    session_hmac=session_hmac,
                    key_hmac=key_hmac,
                    request_id=request_id,
                    state="FAILED",
                )
            except Exception:
                logger.warning("question_failed error_code=DEPENDENCY_UNAVAILABLE")
            snapshot = None
            if request_id is not None:
                try:
                    snapshot = request.app.state.store.request_snapshot(
                        request_id=request_id, session_hmac=session_hmac
                    )
                except Exception:
                    snapshot = None
            if terminal_state == "COMPLETE":
                if snapshot is not None:
                    return snapshot.result
                problem = ApiProblem(
                    503,
                    "DEPENDENCY_UNAVAILABLE",
                    "保存済みの回答を読み出せませんでした。時間を置いて同じ質問送信キーで確認してください。",
                    retryable=True,
                )
            elif terminal_state == "INTERRUPTED":
                problem = _failure_problem(
                    snapshot,
                    KeyState(
                        "INTERRUPTED",
                        request_id,
                        key_state.submit_by,
                        key_state.session_expires_at,
                        key_state.updated_at,
                    ),
                )
            else:
                problem = _query_problem(exc)
            if terminal_state not in {"INTERRUPTED", "COMPLETE"} and snapshot is not None:
                problem = _failure_problem(
                    snapshot,
                    KeyState(
                        "FAILED",
                        request_id,
                        key_state.submit_by,
                        key_state.session_expires_at,
                        key_state.updated_at,
                    ),
                )
            elif terminal_state not in {"INTERRUPTED", "COMPLETE"}:
                # If the failure could not be attached to an audited request,
                # use the same stable fallback that later key replays can derive.
                problem = _failure_problem(None, key_state)
            logger.warning(
                "question_failed error_code=%s elapsed_ms=%d",
                problem.code,
                int((time.monotonic() - started_at) * 1000),
            )
            raise problem from None
        finally:
            reset_public_request_context(token)

    @app.get("/api/requests/by-idempotency-key", response_model=None)
    def get_request_by_key(
        request: Request,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        claims=Depends(_require_session),
    ):
        key = _validate_idempotency_key(idempotency_key, request)
        codec = _session_codec(request)
        session_hmac = codec.session_hmac(claims)
        key_hmac = codec.key_hmac(claims, key)
        try:
            key_state = request.app.state.store.lookup_key(
                session_hmac=session_hmac, key_hmac=key_hmac
            )
        except ApiStoreError as exc:
            raise _store_problem(exc) from exc
        if key_state is None:
            raise ApiProblem(404, "IDEMPOTENCY_KEY_UNKNOWN", "質問の処理結果が見つかりません。")
        if key_state.state == "IN_PROGRESS":
            key_state = request.app.state.store.expire_stuck_request(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                max_age=timedelta(
                    seconds=MAX_QUERY_SECONDS + INTERRUPTION_GRACE_SECONDS
                ),
            )
            if key_state is not None and key_state.state == "IN_PROGRESS":
                return JSONResponse(
                    {"status": "processing"},
                    status_code=202,
                    headers={"Retry-After": "3"},
                )
        snapshot = (
            request.app.state.store.request_snapshot(
                request_id=key_state.request_id, session_hmac=session_hmac
            )
            if key_state and key_state.request_id
            else None
        )
        if key_state.state != "COMPLETE":
            raise _failure_problem(snapshot, key_state)
        if snapshot is None:
            raise ApiProblem(404, "REQUEST_NOT_FOUND", "質問の処理結果が見つかりません。")
        return snapshot.result

    @app.put("/api/requests/{request_id}/feedback", response_model=None)
    def put_feedback(
        request_id: UUID,
        body: FeedbackBody,
        request: Request,
        claims=Depends(_require_same_origin_session),
    ):
        session_hmac = _session_codec(request).session_hmac(claims)
        try:
            request.app.state.store.save_feedback(
                request_id=request_id,
                session_hmac=session_hmac,
                value=body.value,
                comment=body.comment,
            )
        except ApiStoreError as exc:
            raise _store_problem(exc) from exc
        return {"saved": True}

    @app.get(
        "/api/requests/{request_id}/references/{reference_id}/image",
        response_model=None,
    )
    def get_reference_image(
        request_id: UUID,
        reference_id: UUID,
        request: Request,
        claims=Depends(_require_session),
    ):
        session_hmac = _session_codec(request).session_hmac(claims)
        asset = request.app.state.store.authorized_asset(
            request_id=request_id,
            reference_id=reference_id,
            session_hmac=session_hmac,
        )
        if asset is None:
            raise ApiProblem(404, "REFERENCE_NOT_FOUND", "参照画像が見つかりません。")
        try:
            reader = request.app.state.asset_reader or get_asset_reader()
            data = reader.read(asset)
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                image.verify()
        except Exception:
            logger.warning("reference_image_unavailable request_id=%s", request_id)
            raise ApiProblem(404, "REFERENCE_NOT_FOUND", "参照画像が見つかりません。") from None
        if IMAGE_MIME_FORMATS.get(asset.mime_type) != image_format:
            raise ApiProblem(404, "REFERENCE_NOT_FOUND", "参照画像が見つかりません。")
        return Response(
            content=data,
            media_type=asset.mime_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    frontend_dist = app.state.frontend_dist
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str, request: Request):
        if path.startswith("api/") or path == "openapi.json":
            raise ApiProblem(404, "INVALID_REQUEST", "指定されたAPIは見つかりません。")
        frontend = request.app.state.frontend_dist.resolve()
        candidate = (frontend / path).resolve()
        if candidate.is_file() and candidate.is_relative_to(frontend):
            return FileResponse(candidate)
        index = frontend / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-store"})
        raise ApiProblem(404, "INVALID_REQUEST", "指定されたページは見つかりません。")

    return app


def _session_factory():
    from src.persistence.database import get_session_factory

    return get_session_factory()


app = create_app()
