import pytest

from src.provider_retry import classify_provider_error, run_with_503_backoff


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("429 RESOURCE_EXHAUSTED quota exceeded", "rate_limit"),
        ("503 UNAVAILABLE high demand", "unavailable"),
        ("401 invalid API key", "other"),
    ],
)
def test_classify_provider_error(message: str, expected: str) -> None:
    assert classify_provider_error(RuntimeError(message)) == expected


def test_run_with_503_backoff_recovers_with_bounded_exponential_delays() -> None:
    attempts = iter(
        [
            RuntimeError("503 UNAVAILABLE high demand"),
            RuntimeError("503 UNAVAILABLE high demand"),
            "ok",
        ]
    )
    sleeps: list[float] = []

    def operation() -> str:
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    result, retry_count = run_with_503_backoff(operation, sleep=sleeps.append)

    assert result == "ok"
    assert retry_count == 2
    assert sleeps == [5.1, 10.2]


@pytest.mark.parametrize(
    "message",
    ["429 RESOURCE_EXHAUSTED quota exceeded", "401 invalid API key"],
)
def test_run_with_503_backoff_does_not_retry_other_errors(message: str) -> None:
    calls = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match=message):
        run_with_503_backoff(operation, sleep=sleeps.append)

    assert calls == 1
    assert sleeps == []


def test_run_with_503_backoff_stops_after_retry_limit() -> None:
    calls = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("503 UNAVAILABLE high demand")

    with pytest.raises(RuntimeError, match="503 UNAVAILABLE"):
        run_with_503_backoff(operation, sleep=sleeps.append)

    assert calls == 3
    assert sleeps == [5.1, 10.2]
