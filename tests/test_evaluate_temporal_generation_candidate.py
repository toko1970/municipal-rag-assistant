from eval.evaluate_temporal_generation_candidate import (
    _attempt_diagnostics,
    _content_ok,
    _selected_ids,
    _version_resolution_error,
)
from eval.evaluate_contextual_answer_candidate import EvaluationLogger


def test_q291_requires_new_rule_and_rejects_old_rule() -> None:
    assert _content_ok("Q291", "認定された月から支給し、15日以内に提出する。")
    assert not _content_ok(
        "Q291", "認定事由発生日の翌月から支給し、15日以内に提出する。"
    )


def test_comparison_controls_require_both_values() -> None:
    assert _content_ok("Q421", "2km以上から1.5km以上へ変更した。")
    assert not _content_ok("Q421", "1.5km以上へ変更した。")


def test_q186_uses_the_rule_applicable_before_the_revision() -> None:
    assert _content_ok("Q186", "月額15,000円を超える場合に対象となる。")
    assert not _content_ok("Q186", "月額16,000円を超える場合に対象となる。")


def test_q191_applies_the_boundary_and_negative_eligibility() -> None:
    assert _content_ok(
        "Q191", "月額15,000円を超えるという要件を満たさないため、対象外です。"
    )
    assert not _content_ok("Q191", "月額16,000円を超えないため対象外です。")
    assert not _content_ok("Q191", "基準額は15,000円です。")


def test_q286_requires_recognition_month_and_rejects_next_month() -> None:
    assert _content_ok("Q286", "認定された月から支給します。")
    assert not _content_ok("Q286", "認定事由発生日の翌月から支給します。")


def test_version_resolver_failure_is_a_scenario_error() -> None:
    assert _version_resolution_error(None) == ""
    assert (
        _version_resolution_error(
            {"version_resolution": {"status": "RESOLUTION_FAILED"}}
        )
        == "VersionResolverError: structured result unavailable"
    )
    assert (
        _version_resolution_error(
            {
                "version_resolution": {
                    "status": "RESOLUTION_FAILED",
                    "error_summary": "503 UNAVAILABLE",
                }
            }
        )
        == "VersionResolverError: 503 UNAVAILABLE"
    )


def test_single_question_diagnostic_limits_the_scope() -> None:
    assert _selected_ids("Q191") == ("Q191",)


def test_attempt_diagnostics_preserves_partial_generation() -> None:
    logger = EvaluationLogger(
        generation={
            "status": "SUCCESS",
            "response_data": {"claims": [{"text": "生成済み"}]},
            "error_summary": None,
        },
        classification={
            "status": "CLASSIFICATION_FAILED",
            "error_summary": "503 UNAVAILABLE",
        },
    )

    assert _attempt_diagnostics(logger) == {
        "generation_status": "SUCCESS",
        "generation_response_data": {"claims": [{"text": "生成済み"}]},
        "generation_error_summary": None,
        "classification_status": "CLASSIFICATION_FAILED",
        "classification_error_summary": "503 UNAVAILABLE",
    }
