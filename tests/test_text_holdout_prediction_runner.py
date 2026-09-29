from __future__ import annotations

from pathlib import Path

import pytest

from eval.run_text_holdout_predictions import (
    ExternalCallBudget,
    HoldoutEvaluationLogger,
    PacedProvider,
    SharedCallPacer,
    _all_query_texts,
    _failure_type,
    _verify_sealed_documents,
    _logical_calls,
    build_plan,
    freeze_predictions,
    _write_jsonl,
)


def _questions() -> dict:
    return {
        "scenario_count": 1,
        "scenarios": [
            {
                "scenario_id": "TH001",
                "expressions": [
                    {"variant_type": "formal", "question": "通常の質問"},
                    {
                        "variant_type": "paraphrase_or_noisy",
                        "question": "言い換え質問",
                    },
                ],
            }
        ],
    }


def _manifest() -> dict:
    return {
        "state": "CANDIDATE_FROZEN",
        "holdout_id": "holdout",
        "candidate": {"git_commit": "a" * 40},
        "questions": {"expression_count": 2},
        "documents": [{"document_id": "D1", "sha256": "unused"}],
    }


def _candidate() -> dict:
    return {
        "sealed_holdout_accessed": False,
        "execution_policy": {
            "gold_available_to_runner": False,
            "retry_count": 2,
            "retryable_status_codes": [503],
            "retry_backoff_initial_seconds": 5.1,
            "retry_backoff_max_seconds": 10.2,
            "retry_jitter_max_seconds": 1.0,
            "embedding_sdk_attempts": 1,
            "embedding_phase_cooldown_seconds": 60,
            "minimum_generative_call_interval_seconds": 5.1,
            "stop_on_provider_error": True,
            "max_logical_external_calls": 8,
            "max_cost_usd": 0.01,
        },
    }


def test_plan_exposes_bounded_run_without_gold() -> None:
    plan = build_plan(_manifest(), _candidate(), _questions())

    assert plan["expression_count"] == 2
    assert plan["max_logical_external_calls"] == 8
    assert plan["retry_count"] == 2
    assert plan["embedding_sdk_attempts"] == 1
    assert plan["embedding_phase_cooldown_seconds"] == 60
    assert plan["minimum_generative_call_interval_seconds"] == 5.1
    assert plan["gold_available_to_runner"] is False


def test_plan_rejects_gold_access() -> None:
    candidate = _candidate()
    candidate["execution_policy"]["gold_available_to_runner"] = True

    with pytest.raises(ValueError, match="gold"):
        build_plan(_manifest(), candidate, _questions())


def test_query_texts_include_each_question_once_without_trigger() -> None:
    expressions = [
        {"scenario_id": "TH001", "variant_type": "formal", "question": "通常の質問"},
        {"scenario_id": "TH001", "variant_type": "noisy", "question": "通常の質問"},
    ]

    assert _all_query_texts(expressions) == ["通常の質問"]


def test_sealed_document_verification_checks_public_hash(tmp_path: Path) -> None:
    document = tmp_path / "D1.md"
    document.write_text("sealed", encoding="utf-8")
    manifest = _manifest()
    import hashlib

    manifest["documents"][0]["sha256"] = hashlib.sha256(
        document.read_bytes()
    ).hexdigest()

    assert _verify_sealed_documents(manifest, tmp_path) == [document]


def test_freeze_rejects_incomplete_run(tmp_path: Path) -> None:
    import json

    manifest_path = tmp_path / "manifest.json"
    predictions_path = tmp_path / "predictions.jsonl"
    summary_path = tmp_path / "summary.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    predictions_path.write_text("", encoding="utf-8")
    summary_path.write_text(
        json.dumps({"stop_reason": "PROVIDER_ERROR_FAIL_FAST", "run_id": "run"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="完了していない"):
        freeze_predictions(
            manifest_path=manifest_path,
            predictions_path=predictions_path,
            summary_path=summary_path,
        )


def test_logical_call_count_includes_conditional_resolver() -> None:
    logger = HoldoutEvaluationLogger()
    logger.generation = {"status": "SUCCESS"}
    logger.classification_attempts = [{"status": "SUCCESS"}, {"status": "SUCCESS"}]

    assert _logical_calls(logger) == 3


def test_jsonl_writer_serializes_uuid(tmp_path: Path) -> None:
    from uuid import UUID

    path = tmp_path / "records.jsonl"
    _write_jsonl(path, [{"element_id": UUID(int=0)}])

    assert '"element_id": "00000000-0000-0000-0000-000000000000"' in path.read_text()


def test_call_pacer_waits_for_remaining_interval(monkeypatch) -> None:
    clock = iter((10.0, 12.0, 14.1))
    sleeps = []
    monkeypatch.setattr(
        "eval.run_text_holdout_predictions.time.monotonic", lambda: next(clock)
    )
    monkeypatch.setattr("eval.run_text_holdout_predictions.time.sleep", sleeps.append)
    pacer = SharedCallPacer(4.1)

    pacer.wait()
    pacer.wait()

    assert sleeps == pytest.approx([2.1])


def test_failure_type_keeps_candidate_failure_and_retries_provider_failure() -> None:
    assert _failure_type({"status": "FAILED", "error": "ValueError: invalid"}) == (
        "CANDIDATE"
    )
    assert _failure_type(
        {"status": "FAILED", "error": "ServerError: 503 UNAVAILABLE"}
    ) == "PROVIDER"
    assert _failure_type({"status": "SUCCESS", "error": None}) is None


def test_freeze_accepts_candidate_failure_as_scored_execution_failure(
    tmp_path: Path,
) -> None:
    import json

    manifest_path = tmp_path / "manifest.json"
    predictions_path = tmp_path / "predictions.jsonl"
    summary_path = tmp_path / "summary.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    _write_jsonl(
        predictions_path,
        [
            {
                "scenario_id": "TH001",
                "variant_type": "formal",
                "status": "SUCCESS",
                "failure_type": None,
            },
            {
                "scenario_id": "TH001",
                "variant_type": "paraphrase_or_noisy",
                "status": "FAILED",
                "failure_type": "CANDIDATE",
                "error": "ValueError: invalid",
            },
        ],
    )
    summary_path.write_text(
        json.dumps(
            {
                "stop_reason": "COMPLETED",
                "run_id": "run",
                "success_count": 1,
                "failure_count": 1,
                "provider_failure_count": 0,
            }
        ),
        encoding="utf-8",
    )

    frozen = freeze_predictions(
        manifest_path=manifest_path,
        predictions_path=predictions_path,
        summary_path=summary_path,
    )

    assert frozen["state"] == "PREDICTIONS_FROZEN"


def test_paced_provider_retries_only_503_with_exponential_backoff(
    monkeypatch,
) -> None:
    class Provider:
        provider_name = "gemini"
        model = "test"

        def __init__(self) -> None:
            self.calls = 0

        def generate_structured(self, prompt, schema):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("503 UNAVAILABLE high demand")
            return "ok"

    sleeps = []
    monkeypatch.setattr("eval.run_text_holdout_predictions.time.sleep", sleeps.append)
    monkeypatch.setattr(
        "eval.run_text_holdout_predictions.random.uniform", lambda _low, _high: 0.5
    )
    provider = Provider()
    wrapper = PacedProvider(
        provider,
        SharedCallPacer(0),
        ExternalCallBudget(3),
        max_retries=2,
        backoff_initial_seconds=5.1,
        backoff_max_seconds=10.2,
        jitter_max_seconds=1.0,
    )

    assert wrapper.generate_structured("prompt", {}) == "ok"
    assert wrapper.attempt_count == 3
    assert wrapper.retry_count == 2
    assert sleeps == pytest.approx([5.6, 10.7])


def test_paced_provider_does_not_retry_429(monkeypatch) -> None:
    class Provider:
        provider_name = "gemini"
        model = "test"

        def generate_structured(self, prompt, schema):
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    sleeps = []
    monkeypatch.setattr("eval.run_text_holdout_predictions.time.sleep", sleeps.append)
    wrapper = PacedProvider(
        Provider(),
        SharedCallPacer(0),
        ExternalCallBudget(3),
        max_retries=2,
        backoff_initial_seconds=5.1,
        backoff_max_seconds=10.2,
        jitter_max_seconds=1.0,
    )

    with pytest.raises(RuntimeError, match="429"):
        wrapper.generate_structured("prompt", {})

    assert wrapper.attempt_count == 1
    assert wrapper.retry_count == 0
    assert sleeps == []
