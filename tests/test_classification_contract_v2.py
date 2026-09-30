import json
from pathlib import Path
from uuid import UUID

import pytest

from eval.build_classification_contract_v2_development_fixture import build
from src.classification_contract_v2 import (
    decide_classification_v2,
    parse_answer_output_v3,
    parse_classification_output_v2,
    parse_question_contract_v2,
)


EVIDENCE_ID = "00000000-0000-4000-8000-000000000001"
EVIDENCE_UUID = UUID(EVIDENCE_ID)


def _contract(*, facets: int = 1) -> dict:
    return {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "requested_facets": [
            {
                "facet_id": f"facet-{number}",
                "requirement": f"回答項目{number}",
                "answer_type": "fact",
            }
            for number in range(1, facets + 1)
        ],
        "input_facts": [],
        "error_code": None,
    }


def _answer(
    *,
    claim_facets: tuple[str, ...] = ("facet-1",),
    with_claim: bool = True,
    review_type: str | None = None,
) -> dict:
    claims = []
    if with_claim:
        claims.append(
            {
                "claim_id": "claim-1",
                "ordinal": 1,
                "text": "規則に基づく回答です。",
                "facet_ids": list(claim_facets),
                "input_fact_ids": [],
                "calculation_ids": [],
                "evidence_element_ids": [EVIDENCE_ID],
                "evidence_kind": "text",
            }
        )
    conditions = []
    if review_type:
        conditions.append(
            {
                "condition_id": "condition-1",
                "type": review_type,
                "description": "結論を変える確認事項",
                "facet_ids": ["facet-1"],
                "evidence_element_ids": [EVIDENCE_ID],
            }
        )
    return {
        "schema_version": "3.0-candidate",
        "claims": claims,
        "missing_conditions": conditions,
        "date_calculations": [],
    }


def _assessment(
    *,
    facet_id: str = "facet-1",
    claim_ids: tuple[str, ...] = ("claim-1",),
    claim_support: str = "fully_supported",
    evidence_coverage: str = "sufficient",
    review_type: str | None = None,
) -> dict:
    reviews = []
    if review_type:
        reviews.append(
            {
                "review_id": "review-1",
                "type": review_type,
                "description": "結論を変える確認事項",
                "condition_ids": ["condition-1"],
                "evidence_element_ids": [EVIDENCE_ID],
            }
        )
    return {
        "facet_id": facet_id,
        "claim_ids": list(claim_ids),
        "claim_support": claim_support,
        "evidence_coverage": evidence_coverage,
        "human_review_requirements": reviews,
        "evidence_element_ids": [EVIDENCE_ID]
        if evidence_coverage == "sufficient"
        else [],
        "confidence": 0.9,
    }


def _classification(*assessments: dict) -> dict:
    return {
        "schema_version": "2.0-candidate",
        "status": "SUCCESS",
        "facet_assessments": list(assessments),
        "confidence": 0.9,
        "error_code": None,
    }


def _decide(contract: dict, answer: dict, classification: dict):
    return decide_classification_v2(
        parse_question_contract_v2(contract),
        parse_answer_output_v3(answer),
        parse_classification_output_v2(classification),
        {EVIDENCE_UUID},
    )


@pytest.mark.parametrize(
    ("review_type", "expected_label"),
    [
        (None, "根拠十分"),
        ("case_fact", "判断要"),
        ("policy_judgment", "判断要"),
        ("version_conflict", "判断要"),
    ],
)
def test_v2_decision_table_for_supported_answers(
    review_type: str | None, expected_label: str
) -> None:
    decision = _decide(
        _contract(),
        _answer(review_type=review_type),
        _classification(_assessment(review_type=review_type)),
    )

    assert decision.status == "SUCCESS"
    assert decision.label == expected_label


def test_document_shortage_is_not_generation_failure() -> None:
    decision = _decide(
        _contract(),
        _answer(with_claim=False),
        _classification(
            _assessment(
                claim_ids=(),
                claim_support="no_claim",
                evidence_coverage="insufficient",
            )
        ),
    )

    assert decision.status == "SUCCESS"
    assert decision.label == "文書不足"


def test_th011_shape_is_generation_incomplete_not_document_shortage() -> None:
    classification = _classification(
        _assessment(facet_id="facet-1"),
        _assessment(
            facet_id="facet-2",
            claim_ids=(),
            claim_support="no_claim",
        ),
    )
    decision = _decide(
        _contract(facets=2),
        _answer(claim_facets=("facet-1",)),
        classification,
    )

    assert decision.status == "GENERATION_INCOMPLETE"
    assert decision.label is None


def test_opened_holdout_mechanism_fixture_matches_saved_artifact() -> None:
    path = Path("eval/classification_contract_v2_development_cases.json")

    assert json.loads(path.read_text(encoding="utf-8")) == build()


def test_opened_holdout_mechanism_fixture_keeps_failure_families_separate() -> None:
    fixture = build()
    decisions = {}
    for row in fixture["cases"]:
        decision = decide_classification_v2(
            parse_question_contract_v2(row["question_contract"]),
            parse_answer_output_v3(row["answer_v3"]),
            parse_classification_output_v2(row["classification_v2"]),
            {UUID(value) for value in row["retrieved_element_ids"]},
        )
        decisions[row["scenario_id"]] = decision
        assert decision.status == row["expected_status"]
        assert decision.label == row["expected_label"]

    assert decisions["TH011"].status == "GENERATION_INCOMPLETE"
    assert decisions["TH025"].label == "判断要"
    assert decisions["TH031"].label == "判断要"


def test_document_shortage_cannot_be_justified_as_human_review() -> None:
    decision = _decide(
        _contract(),
        _answer(review_type="case_fact"),
        _classification(
            _assessment(
                claim_support="fully_supported",
                evidence_coverage="insufficient",
                review_type="case_fact",
            )
        ),
    )

    assert decision.status == "PIPELINE_INCONSISTENCY"
    assert decision.invariant_code == "REVIEW_WITHOUT_DECISION_BASIS"


def test_unknown_claim_reference_fails_closed() -> None:
    decision = _decide(
        _contract(),
        _answer(),
        _classification(_assessment(claim_ids=("claim-2",))),
    )

    assert decision.status == "PIPELINE_INCONSISTENCY"
    assert decision.invariant_code == "UNKNOWN_CLAIM"


def test_review_type_must_match_referenced_condition() -> None:
    assessment = _assessment(review_type="case_fact")
    assessment["human_review_requirements"][0]["type"] = "policy_judgment"

    decision = _decide(
        _contract(),
        _answer(review_type="case_fact"),
        _classification(assessment),
    )

    assert decision.status == "PIPELINE_INCONSISTENCY"
    assert decision.invariant_code == "REVIEW_CONDITION_TYPE_MISMATCH"


def test_every_requested_facet_must_be_assessed_once() -> None:
    decision = _decide(
        _contract(facets=2),
        _answer(),
        _classification(_assessment()),
    )

    assert decision.status == "PIPELINE_INCONSISTENCY"
    assert decision.invariant_code == "FACET_ASSESSMENT_MISMATCH"


def test_question_contract_rejects_epistemic_status() -> None:
    contract = _contract()
    contract["input_facts"] = [
        {
            "fact_id": "fact-1",
            "text": "予約日が不明",
            "fact_type": "date",
            "epistemic_status": "unresolved",
            "applies_to_facet_ids": ["facet-1"],
        }
    ]

    with pytest.raises(ValueError, match="schema"):
        parse_question_contract_v2(contract)
