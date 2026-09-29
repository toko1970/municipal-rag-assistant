from uuid import uuid4

import pytest

from src.answering import (
    derive_label,
    parse_answer_output,
    parse_classification_output,
    render_display_answer,
    validate_answer_evidence,
)


def answer_data(evidence_id: str, missing: list[str] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "claims": [
            {
                "claim_id": "claim-1",
                "ordinal": 1,
                "text": "給与は毎月21日に支給されます。",
                "evidence_element_ids": [evidence_id],
                "evidence_kind": "text",
            }
        ],
        "missing_conditions": missing or [],
    }


def classification_data(**overrides: bool) -> dict:
    factors = {
        "retrieval_sufficient": True,
        "answer_fully_supported": True,
        "requires_case_facts": False,
        "requires_policy_judgment": False,
        "version_conflict": False,
    }
    factors.update(overrides)
    return {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "factors": factors,
        "confidence": 0.95,
        "error_code": None,
    }


def test_renders_sufficient_claims_from_structured_inputs() -> None:
    evidence_id = uuid4()
    answer = parse_answer_output(answer_data(str(evidence_id)))
    validate_answer_evidence(answer, {evidence_id})

    display = render_display_answer(
        answer, parse_classification_output(classification_data())
    )

    assert display.label == "根拠十分"
    assert "給与は毎月21日に支給されます。" in display.text


def test_judgment_hides_claims_when_global_support_is_false() -> None:
    evidence_id = uuid4()
    answer = parse_answer_output(answer_data(str(evidence_id), ["居住実態"]))
    classification = parse_classification_output(
        classification_data(
            answer_fully_supported=False,
            requires_case_facts=True,
        )
    )

    display = render_display_answer(answer, classification)

    assert display.label == "判断要"
    assert not display.visible_claims
    assert "個別事情の確認" in display.text


def test_insufficient_never_displays_generator_claims() -> None:
    evidence_id = uuid4()
    answer = parse_answer_output(answer_data(str(evidence_id)))
    classification = parse_classification_output(
        classification_data(retrieval_sufficient=False)
    )

    display = render_display_answer(answer, classification)

    assert display.label == "文書不足"
    assert "給与は毎月21日に支給されます。" not in display.text
    assert "今回取得した根拠" in display.text


def test_case_fact_flag_takes_precedence_over_retrieval_failure() -> None:
    classification = parse_classification_output(
        classification_data(
            retrieval_sufficient=False,
            answer_fully_supported=False,
            requires_case_facts=True,
        )
    )

    assert derive_label(classification.factors) == "判断要"


def test_rejects_citation_not_in_current_retrieval() -> None:
    answer = parse_answer_output(answer_data(str(uuid4())))

    with pytest.raises(ValueError, match="今回取得していない"):
        validate_answer_evidence(answer, {uuid4()})


def test_rejects_non_contiguous_claim_ordinals() -> None:
    data = answer_data(str(uuid4()))
    data["claims"][0]["claim_id"] = "claim-2"
    data["claims"][0]["ordinal"] = 2

    with pytest.raises(ValueError, match="連続"):
        parse_answer_output(data)
