import json
from pathlib import Path

import jsonschema
import pytest

from eval.build_classification_rubric_v2_audit import ROOT, build


SCHEMA_DIR = ROOT / "design" / "schemas"


def test_candidate_schemas_are_valid_draft_2020_12() -> None:
    for name in (
        "question-contract-v1.schema.json",
        "answer-output-v3-candidate.schema.json",
        "classification-output-v2-candidate.schema.json",
    ):
        schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)


def test_candidate_schemas_accept_a_linked_success_path() -> None:
    evidence_id = "00000000-0000-4000-8000-000000000001"
    examples = {
        "question-contract-v1.schema.json": {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "requested_facets": [
                {
                    "facet_id": "facet-1",
                    "requirement": "補填額",
                    "answer_type": "amount",
                }
            ],
            "input_facts": [
                {
                    "fact_id": "fact-1",
                    "text": "予約日は2027年7月31日",
                    "fact_type": "date",
                    "applies_to_facet_ids": ["facet-1"],
                }
            ],
            "error_code": None,
        },
        "answer-output-v3-candidate.schema.json": {
            "schema_version": "3.0-candidate",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "補填額は1,500円です。",
                    "facet_ids": ["facet-1"],
                    "input_fact_ids": ["fact-1"],
                    "calculation_ids": [],
                    "evidence_element_ids": [evidence_id],
                    "evidence_kind": "text",
                }
            ],
            "missing_conditions": [],
            "date_calculations": [],
        },
        "classification-output-v2-candidate.schema.json": {
            "schema_version": "2.0-candidate",
            "status": "SUCCESS",
            "facet_assessments": [
                {
                    "facet_id": "facet-1",
                    "claim_ids": ["claim-1"],
                    "claim_support": "fully_supported",
                    "evidence_coverage": "sufficient",
                    "human_review_requirements": [],
                    "evidence_element_ids": [evidence_id],
                    "confidence": 0.9,
                }
            ],
            "confidence": 0.9,
            "error_code": None,
        },
    }

    for name, example in examples.items():
        schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(example)


def test_question_input_cannot_directly_encode_epistemic_classification() -> None:
    schema = json.loads(
        (SCHEMA_DIR / "question-contract-v1.schema.json").read_text(encoding="utf-8")
    )
    invalid = {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "requested_facets": [
            {"facet_id": "facet-1", "requirement": "補填額", "answer_type": "amount"}
        ],
        "input_facts": [
            {
                "fact_id": "fact-1",
                "text": "予約日が不明",
                "fact_type": "date",
                "epistemic_status": "unresolved",
                "applies_to_facet_ids": ["facet-1"],
            }
        ],
        "error_code": None,
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(invalid)


def test_review_requirement_needs_document_evidence() -> None:
    schema = json.loads(
        (SCHEMA_DIR / "classification-output-v2-candidate.schema.json").read_text(
            encoding="utf-8"
        )
    )
    invalid = {
        "schema_version": "2.0-candidate",
        "status": "SUCCESS",
        "facet_assessments": [
            {
                "facet_id": "facet-1",
                "claim_ids": ["claim-1"],
                "claim_support": "fully_supported",
                "evidence_coverage": "sufficient",
                "human_review_requirements": [
                    {
                        "review_id": "review-1",
                        "type": "case_fact",
                        "description": "予約日",
                        "condition_ids": [],
                        "evidence_element_ids": [],
                    }
                ],
                "evidence_element_ids": ["00000000-0000-4000-8000-000000000001"],
                "confidence": 0.9,
            }
        ],
        "confidence": 0.9,
        "error_code": None,
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(invalid)


def test_opened_holdout_audit_preserves_labels_and_exposes_coverage_gaps() -> None:
    audit = build()

    assert audit["scenario_count"] == 50
    assert audit["expression_count"] == 100
    assert audit["label_counts"] == {
        "根拠十分": 30,
        "文書不足": 10,
        "判断要": 10,
    }
    assert audit["label_change_count"] == 0
    assert audit["human_review_reason_counts"] == {
        "case_fact": 10,
        "policy_judgment": 0,
        "version_conflict": 0,
    }
    assert audit["coverage_gaps"] == ["policy_judgment", "version_conflict"]


def test_insufficient_evidence_never_has_human_review_requirement() -> None:
    audit = build()

    for row in audit["scenarios"]:
        if row["oracle_evidence_coverage"] == "insufficient":
            assert row["human_review_requirements"] == []
            assert row["expected_claim_support"] == "no_claim"


def test_committed_audit_matches_the_reproducible_builder() -> None:
    committed = json.loads(
        (Path(ROOT) / "eval" / "classification_rubric_v2_audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert committed == build()


def test_boundary_controls_cover_each_new_semantic_boundary() -> None:
    fixture = json.loads(
        (Path(ROOT) / "eval" / "classification_rubric_v2_boundary_cases.json").read_text(
            encoding="utf-8"
        )
    )
    cases = fixture["cases"]

    assert len(cases) == 8
    assert {row["expected_review_type"] for row in cases} == {
        None,
        "case_fact",
        "policy_judgment",
        "version_conflict",
    }
    assert {row["expected_result"] for row in cases} == {
        "根拠十分",
        "判断要",
        "文書不足",
        "GENERATION_INCOMPLETE",
    }
