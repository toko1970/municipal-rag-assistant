"""Data types and errors for the facet classification contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID


@dataclass(frozen=True)
class QuestionFacetV2:
    facet_id: str
    requirement: str
    answer_type: str


@dataclass(frozen=True)
class InputFactV2:
    fact_id: str
    text: str
    fact_type: str
    facet_ids: tuple[str, ...]


@dataclass(frozen=True)
class QuestionContractV2:
    facets: tuple[QuestionFacetV2, ...]
    input_facts: tuple[InputFactV2, ...]


@dataclass(frozen=True)
class AnswerClaimV3:
    claim_id: str
    ordinal: int
    text: str
    facet_ids: tuple[str, ...]
    input_fact_ids: tuple[str, ...]
    calculation_ids: tuple[str, ...]
    evidence_element_ids: tuple[UUID, ...]
    evidence_kind: str
    claim_type: str
    depends_on_condition_ids: tuple[str, ...]


@dataclass(frozen=True)
class MissingConditionV3:
    condition_id: str
    condition_type: str
    description: str
    facet_ids: tuple[str, ...]
    evidence_element_ids: tuple[UUID, ...]
    blocking_claim_ids: tuple[str, ...]


@dataclass(frozen=True)
class DateCalculationV3:
    calculation_id: str
    result_label: str
    facet_ids: tuple[str, ...]
    anchor_date: date
    offset_value: int
    offset_unit: str
    counting_rule: str
    cutoff_time: time | None
    evidence_element_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class StructuredAnswerV3:
    claims: tuple[AnswerClaimV3, ...]
    missing_conditions: tuple[MissingConditionV3, ...]
    date_calculations: tuple[DateCalculationV3, ...]


@dataclass(frozen=True)
class HumanReviewRequirementV2:
    review_id: str
    requirement_type: str
    description: str
    condition_ids: tuple[str, ...]
    evidence_element_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class FacetAssessmentV2:
    facet_id: str
    claim_ids: tuple[str, ...]
    claim_support: str
    evidence_coverage: str
    human_review_requirements: tuple[HumanReviewRequirementV2, ...]
    evidence_element_ids: tuple[UUID, ...]
    confidence: float


@dataclass(frozen=True)
class ClassificationResultV2:
    facet_assessments: tuple[FacetAssessmentV2, ...]
    confidence: float


@dataclass(frozen=True)
class ClassificationDecisionV2:
    status: str
    label: str | None
    invariant_code: str | None = None


@dataclass(frozen=True)
class DisplayAnswerV2:
    label: str | None
    text: str
    visible_claims: tuple[AnswerClaimV3, ...]
    status: str
    invariant_code: str | None = None


class ClassificationContractV2Error(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code
