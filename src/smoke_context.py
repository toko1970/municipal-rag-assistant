"""Candidate-smoke-only absolute deadlines and bounded progress events."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Callable, Iterator
import re
import time


_ACTIVE_DEADLINE: ContextVar["SmokeDeadline | None"] = ContextVar(
    "smoke_deadline", default=None
)
_ACTIVE_PROGRESS: ContextVar[Callable[[dict[str, object]], None] | None] = ContextVar(
    "smoke_progress", default=None
)
_PROGRESS_META: ContextVar[tuple[str, int, float, Callable[[], float]] | None] = (
    ContextVar("smoke_progress_meta", default=None)
)
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SAFE_STAGES = frozenset(
    {
        "RAG_QUERY",
        "EMBEDDING",
        "RETRIEVAL",
        "RETRIEVAL_RECORD",
        "CONTEXT_BUILD",
        "GENERATOR_SETUP",
        "VISUAL_METADATA",
        "VISUAL_ASSET_LOAD",
        "GENERATION",
        "ANSWER_VALIDATION",
    }
)
_SAFE_STATUSES = frozenset({"started", "completed", "failed", "timed_out"})


@dataclass(frozen=True)
class SmokeDeadline:
    expires_at: float
    clock: Callable[[], float] = time.monotonic

    def remaining_seconds(self) -> float:
        remaining = self.expires_at - self.clock()
        if remaining <= 0:
            raise TimeoutError("candidate smoke deadline exceeded")
        return remaining

    @staticmethod
    def current() -> "SmokeDeadline":
        deadline = _ACTIVE_DEADLINE.get()
        if deadline is None:
            raise RuntimeError("no candidate smoke deadline is active")
        deadline.remaining_seconds()
        return deadline


@contextmanager
def bind_smoke_context(
    deadline: SmokeDeadline,
    progress: Callable[[dict[str, object]], None] | None = None,
    *,
    case_id: str = "unknown",
    attempt: int = 1,
    started_at: float | None = None,
) -> Iterator[None]:
    deadline_token: Token = _ACTIVE_DEADLINE.set(deadline)
    progress_token: Token = _ACTIVE_PROGRESS.set(progress)
    meta_token: Token = _PROGRESS_META.set(
        (
            case_id,
            attempt,
            started_at if started_at is not None else deadline.clock(),
            deadline.clock,
        )
    )
    try:
        yield
    finally:
        _ACTIVE_PROGRESS.reset(progress_token)
        _PROGRESS_META.reset(meta_token)
        _ACTIVE_DEADLINE.reset(deadline_token)


def active_deadline() -> SmokeDeadline | None:
    return _ACTIVE_DEADLINE.get()


def remaining_seconds() -> float | None:
    deadline = active_deadline()
    return deadline.remaining_seconds() if deadline else None


def emit_progress(
    *,
    case_id: str,
    stage: str,
    attempt: int,
    started_at: float,
    status: str,
    request_id: str | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    callback = _ACTIVE_PROGRESS.get()
    if callback is None or stage not in _SAFE_STAGES or status not in _SAFE_STATUSES:
        return
    event: dict[str, object] = {
        "event": "candidate_smoke_progress",
        "case_id": case_id,
        "stage": stage,
        "attempt": attempt,
        "elapsed_ms": max(0, int((clock() - started_at) * 1000)),
        "status": status,
    }
    if request_id and _SAFE_ID.fullmatch(request_id):
        event["request_id"] = request_id
    callback(event)


def emit_stage(stage: str, status: str, request_id: str | None = None) -> None:
    meta = _PROGRESS_META.get()
    if meta is None:
        return
    case_id, attempt, started_at, clock = meta
    emit_progress(
        case_id=case_id,
        stage=stage,
        attempt=attempt,
        started_at=started_at,
        status=status,
        request_id=request_id,
        clock=clock,
    )
