from __future__ import annotations

from pathlib import Path

import pytest

from eval.run_text_holdout_predictions import (
    HoldoutEvaluationLogger,
    _all_query_texts,
    _verify_sealed_documents,
    _logical_calls,
    build_plan,
    freeze_predictions,
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
            "retry_count": 0,
            "stop_on_provider_error": True,
            "max_logical_external_calls": 8,
            "max_cost_usd": 0.01,
        },
    }


def test_plan_exposes_bounded_run_without_gold() -> None:
    plan = build_plan(_manifest(), _candidate(), _questions())

    assert plan["expression_count"] == 2
    assert plan["max_logical_external_calls"] == 8
    assert plan["retry_count"] == 0
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
