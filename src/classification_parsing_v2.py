"""Schema validation and parsing for v2 question and answer contracts."""

from __future__ import annotations

import json
from datetime import date, time
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import jsonschema

from src.classification_contract_v2_types import (
    AnswerClaimV3,
    ClassificationResultV2,
    DateCalculationV3,
    FacetAssessmentV2,
    HumanReviewRequirementV2,
    InputFactV2,
    MissingConditionV3,
    QuestionContractV2,
    QuestionFacetV2,
    StructuredAnswerV3,
)


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "design" / "schemas"


@lru_cache(maxsize=3)
def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validate_schema(name: str, data: dict[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator(
            _schema(name), format_checker=jsonschema.FormatChecker()
        ).validate(data)
    except jsonschema.ValidationError as exc:
        location = ".".join(map(str, exc.absolute_path)) or "top-level"
        raise ValueError(f"{name}違反 ({location}): {exc.message}") from exc


def _uuid_tuple(values: list[str]) -> tuple[UUID, ...]:
    return tuple(UUID(value) for value in values)


def parse_question_contract_v2(data: dict[str, Any]) -> QuestionContractV2:
    _validate_schema("question-contract-v1.schema.json", data)
    if data["status"] != "SUCCESS":
        raise ValueError(str(data.get("error_code") or "CONTRACT_FAILED"))
    return QuestionContractV2(
        facets=tuple(
            QuestionFacetV2(
                facet_id=row["facet_id"],
                requirement=row["requirement"].strip(),
                answer_type=row["answer_type"],
            )
            for row in data["requested_facets"]
        ),
        input_facts=tuple(
            InputFactV2(
                fact_id=row["fact_id"],
                text=row["text"].strip(),
                fact_type=row["fact_type"],
                facet_ids=tuple(row["applies_to_facet_ids"]),
            )
            for row in data["input_facts"]
        ),
    )


def parse_answer_output_v3(data: dict[str, Any]) -> StructuredAnswerV3:
    _validate_schema("answer-output-v3-candidate.schema.json", data)
    return StructuredAnswerV3(
        claims=tuple(
            AnswerClaimV3(
                claim_id=row["claim_id"],
                ordinal=row["ordinal"],
                text=row["text"].strip(),
                facet_ids=tuple(row["facet_ids"]),
                input_fact_ids=tuple(row["input_fact_ids"]),
                calculation_ids=tuple(row["calculation_ids"]),
                evidence_element_ids=_uuid_tuple(row["evidence_element_ids"]),
                evidence_kind=row["evidence_kind"],
                claim_type=row["claim_type"],
                depends_on_condition_ids=tuple(row["depends_on_condition_ids"]),
            )
            for row in data["claims"]
        ),
        missing_conditions=tuple(
            MissingConditionV3(
                condition_id=row["condition_id"],
                condition_type=row["type"],
                description=row["description"].strip(),
                facet_ids=tuple(row["facet_ids"]),
                evidence_element_ids=_uuid_tuple(row["evidence_element_ids"]),
                blocking_claim_ids=tuple(row["blocking_claim_ids"]),
            )
            for row in data["missing_conditions"]
        ),
        date_calculations=tuple(
            DateCalculationV3(
                calculation_id=row["calculation_id"],
                result_label=row["result_label"].strip(),
                facet_ids=tuple(row["facet_ids"]),
                anchor_date=date.fromisoformat(row["anchor_date"]),
                offset_value=row["offset_value"],
                offset_unit=row["offset_unit"],
                counting_rule=row["counting_rule"],
                cutoff_time=(
                    time.fromisoformat(row["cutoff_time"])
                    if row["cutoff_time"] is not None
                    else None
                ),
                evidence_element_ids=_uuid_tuple(row["evidence_element_ids"]),
            )
            for row in data["date_calculations"]
        ),
    )


def parse_classification_output_v2(data: dict[str, Any]) -> ClassificationResultV2:
    _validate_schema("classification-output-v2-candidate.schema.json", data)
    if data["status"] != "SUCCESS":
        raise ValueError(str(data.get("error_code") or "CLASSIFICATION_FAILED"))
    return ClassificationResultV2(
        facet_assessments=tuple(
            FacetAssessmentV2(
                facet_id=row["facet_id"],
                claim_ids=tuple(row["claim_ids"]),
                claim_support=row["claim_support"],
                evidence_coverage=row["evidence_coverage"],
                human_review_requirements=tuple(
                    HumanReviewRequirementV2(
                        review_id=review["review_id"],
                        requirement_type=review["type"],
                        description=review["description"].strip(),
                        condition_ids=tuple(review["condition_ids"]),
                        evidence_element_ids=_uuid_tuple(
                            review["evidence_element_ids"]
                        ),
                    )
                    for review in row["human_review_requirements"]
                ),
                evidence_element_ids=_uuid_tuple(row["evidence_element_ids"]),
                confidence=float(row["confidence"]),
            )
            for row in data["facet_assessments"]
        ),
        confidence=float(data["confidence"]),
    )
