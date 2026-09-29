from eval.compare_version_conflict_prompt import (
    INSUFFICIENT_CONTROL_IDS,
    OTHER_JUDGMENT_CONTROL_IDS,
    SELECTED_IDS,
    TARGET_IDS,
    TRUE_VERSION_CONFLICT_IDS,
    build_version_conflict_prompt,
    summarize,
)


def test_experiment_has_fixed_target_and_control_counts() -> None:
    assert len(TARGET_IDS) == 7
    assert len(TRUE_VERSION_CONFLICT_IDS) == 1
    assert len(OTHER_JUDGMENT_CONTROL_IDS) == 7
    assert len(INSUFFICIENT_CONTROL_IDS) == 2
    assert len(SELECTED_IDS) == 17


def test_candidate_changes_only_version_conflict_boundary() -> None:
    prompt = build_version_conflict_prompt(
        "2025年10月ならどちらを適用しますか？",
        [{"content": "2025年10月1日から新版を適用する。"}],
        {"schema_version": "1.0", "claims": [], "missing_conditions": []},
    )

    assert "他の4要因の判定規則は変更しません" in prompt
    assert "適用版を一意に決められない" in prompt
    assert "2025年10月1日から新版" in prompt
    assert "基準日がなく" in prompt


def test_gate_requires_target_improvement_without_control_regression() -> None:
    records = [
        {
            "question_id": "Q121",
            "role": "target_resolved_version",
            "prompt": "baseline",
            "correct": False,
            "error": None,
        },
        {
            "question_id": "Q121",
            "role": "target_resolved_version",
            "prompt": "candidate",
            "correct": True,
            "error": None,
        },
        {
            "question_id": "Q176",
            "role": "control_true_version_conflict",
            "prompt": "baseline",
            "correct": True,
            "error": None,
        },
        {
            "question_id": "Q176",
            "role": "control_true_version_conflict",
            "prompt": "candidate",
            "correct": True,
            "error": None,
        },
    ]

    result = summarize(records, case_count=2)

    assert result["gate"] == {
        "target_improvement_count": 1,
        "control_regression_count": 0,
        "passed": True,
    }
    assert result["stop_reason"] == "COMPLETED"


def test_provider_error_is_reported_as_fail_fast() -> None:
    result = summarize(
        [
            {
                "question_id": "Q121",
                "role": "target_resolved_version",
                "prompt": "baseline",
                "correct": False,
                "error": "RESOURCE_EXHAUSTED",
            }
        ],
        case_count=17,
    )

    assert result["error_count"] == 1
    assert result["stop_reason"] == "PROVIDER_ERROR_FAIL_FAST"
    assert result["gate"]["passed"] is False
