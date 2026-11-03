"""Per-request ownership context for existing persistence entry points."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class PublicRequestContext:
    session_hmac: str
    session_expires_at: datetime
    request_id: UUID | None = None


_current_context: ContextVar[PublicRequestContext | None] = ContextVar(
    "public_request_context", default=None
)


def bind_public_request_context(
    session_hmac: str, session_expires_at: datetime
) -> Token:
    return _current_context.set(
        PublicRequestContext(session_hmac, session_expires_at)
    )


def reset_public_request_context(token: Token) -> None:
    _current_context.reset(token)


def current_public_request_context() -> PublicRequestContext | None:
    return _current_context.get()


def set_public_request_id(request_id: UUID) -> None:
    context = _current_context.get()
    if context is not None:
        _current_context.set(replace(context, request_id=request_id))
