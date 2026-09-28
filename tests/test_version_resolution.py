from uuid import uuid4

import pytest

from eval.evaluate_version_resolver import (
    DIAGNOSTIC_IDS,
    SELECTED_IDS,
    TARGET_IDS,
    TRUE_CONFLICT_IDS,
    build_version_resolution_prompt,
    summarize,
)
from src.version_resolution import parse_version_resolution


def response(*, conflict: bool, basis: str) -> dict:
    return {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "version_conflict": conflict,
        "resolution_basis": basis,
        "evidence_element_ids": [str(uuid4())],
        "confidence": 0.9,
        "error_code": None,
    }


def test_version_resolution_contract_accepts_resolved_and_unresolved() -> None:
    resolved = parse_version_resolution(
        response(conflict=False, basis="effective_period")
    )
    unresolved = parse_version_resolution(response(conflict=True, basis="unresolved"))

    assert resolved.version_conflict is False
    assert unresolved.version_conflict is True

    single_source = parse_version_resolution(
        response(conflict=False, basis="single_applicable_source")
    )
    assert single_source.resolution_basis == "single_applicable_source"


def test_version_resolution_contract_rejects_conflicting_basis() -> None:
    with pytest.raises(ValueError, match="矛盾"):
        parse_version_resolution(response(conflict=True, basis="question_date"))


def test_resolver_scope_and_prompt_are_fixed() -> None:
    assert len(TARGET_IDS) == 7
    assert len(TRUE_CONFLICT_IDS) == 1
    assert len(DIAGNOSTIC_IDS) == 1
    assert len(SELECTED_IDS) == 9
    prompt = build_version_resolution_prompt("質問", [{"content": "根拠"}], {})
    assert "版が一意に決まるかだけ" in prompt
    assert "個別事情" in prompt
    assert "複数版が取得された事実だけ" in prompt
    assert "single_applicable_source" in prompt


def test_gate_requires_all_targets_and_true_conflict_control() -> None:
    records = [
        *[
            {
                "role": "target_resolved_version",
                "resolver_correct": True,
                "error": None,
            }
            for _ in range(7)
        ],
        {
            "role": "control_true_version_conflict",
            "resolver_correct": True,
            "error": None,
        },
        {
            "role": "diagnostic_retrieval_failure",
            "resolver_correct": False,
            "error": None,
        },
    ]

    result = summarize(records, case_count=9)

    assert result["gate"]["passed"] is True
    assert result["diagnostic_correct"] == 0
