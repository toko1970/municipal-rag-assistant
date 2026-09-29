"""Bounded retry policy for transient Gemini provider failures."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Literal, TypeVar


DEFAULT_MAX_503_RETRIES = 2
DEFAULT_BACKOFF_INITIAL_SECONDS = 5.1
DEFAULT_BACKOFF_MAX_SECONDS = 10.2

ProviderErrorKind = Literal["rate_limit", "unavailable", "other"]
T = TypeVar("T")


def classify_provider_error(error: Exception) -> ProviderErrorKind:
    """Classify provider errors without treating every API failure as quota usage."""

    message = str(error).upper()
    if "429" in message or "RESOURCE_EXHAUSTED" in message:
        return "rate_limit"
    if "503" in message and ("UNAVAILABLE" in message or "HIGH DEMAND" in message):
        return "unavailable"
    return "other"


def run_with_503_backoff(
    operation: Callable[[], T],
    *,
    sleep: Callable[[float], None] = time.sleep,
    max_retries: int = DEFAULT_MAX_503_RETRIES,
    backoff_initial_seconds: float = DEFAULT_BACKOFF_INITIAL_SECONDS,
    backoff_max_seconds: float = DEFAULT_BACKOFF_MAX_SECONDS,
) -> tuple[T, int]:
    """Retry only transient 503 failures using a bounded exponential delay."""

    for retry_count in range(max_retries + 1):
        try:
            return operation(), retry_count
        except Exception as error:
            if (
                retry_count >= max_retries
                or classify_provider_error(error) != "unavailable"
            ):
                raise
            delay = min(
                backoff_initial_seconds * (2**retry_count),
                backoff_max_seconds,
            )
            print(
                json.dumps(
                    {
                        "event": "provider_503_retry",
                        "retry": retry_count + 1,
                        "max_retries": max_retries,
                        "backoff_seconds": delay,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            sleep(delay)
    raise AssertionError("unreachable")
