"""Candidate classification contract v2 parsing and deterministic decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, time
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import jsonschema

from config import (
    ANSWER_TYPE_INSUFFICIENT,
    ANSWER_TYPE_NEEDS_JUDGMENT,
    ANSWER_TYPE_SUFFICIENT,
)


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "design" / "schemas"


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


def _require_contiguous(ids: list[str], *, prefix: str, code: str) -> None:
    expected = [f"{prefix}-{index}" for index in range(1, len(ids) + 1)]
    if ids != expected:
        raise ClassificationContractV2Error(
            f"{prefix} IDは1から連続させてください", code=code
        )


def validate_classification_contract_v2(
    contract: QuestionContractV2,
    answer: StructuredAnswerV3,
    classification: ClassificationResultV2,
    retrieved_element_ids: set[UUID],
) -> None:
    _require_contiguous(
        [row.facet_id for row in contract.facets],
        prefix="facet",
        code="INVALID_FACET_SEQUENCE",
    )
    _require_contiguous(
        [row.fact_id for row in contract.input_facts],
        prefix="fact",
        code="INVALID_FACT_SEQUENCE",
    )
    _require_contiguous(
        [row.claim_id for row in answer.claims],
        prefix="claim",
        code="INVALID_CLAIM_SEQUENCE",
    )
    if [row.ordinal for row in answer.claims] != list(range(1, len(answer.claims) + 1)):
        raise ClassificationContractV2Error(
            "claim ordinalは1から連続させてください", code="INVALID_CLAIM_ORDINAL"
        )
    _require_contiguous(
        [row.condition_id for row in answer.missing_conditions],
        prefix="condition",
        code="INVALID_CONDITION_SEQUENCE",
    )
    _require_contiguous(
        [row.calculation_id for row in answer.date_calculations],
        prefix="date",
        code="INVALID_CALCULATION_SEQUENCE",
    )

    facet_ids = {row.facet_id for row in contract.facets}
    fact_ids = {row.fact_id for row in contract.input_facts}
    claims_by_id = {row.claim_id: row for row in answer.claims}
    conditions_by_id = {row.condition_id: row for row in answer.missing_conditions}
    calculation_ids = {row.calculation_id for row in answer.date_calculations}

    def require_known(actual: set[Any], expected: set[Any], code: str) -> None:
        if unknown := actual - expected:
            raise ClassificationContractV2Error(
                f"未知の参照があります: {sorted(map(str, unknown))}", code=code
            )

    for fact in contract.input_facts:
        require_known(set(fact.facet_ids), facet_ids, "UNKNOWN_FACT_FACET")
    for claim in answer.claims:
        require_known(set(claim.facet_ids), facet_ids, "UNKNOWN_CLAIM_FACET")
        require_known(set(claim.input_fact_ids), fact_ids, "UNKNOWN_INPUT_FACT")
        require_known(
            set(claim.calculation_ids), calculation_ids, "UNKNOWN_CALCULATION"
        )
        require_known(
            set(claim.evidence_element_ids), retrieved_element_ids, "UNKNOWN_EVIDENCE"
        )
    for condition in answer.missing_conditions:
        require_known(set(condition.facet_ids), facet_ids, "UNKNOWN_CONDITION_FACET")
        require_known(
            set(condition.evidence_element_ids),
            retrieved_element_ids,
            "UNKNOWN_EVIDENCE",
        )
    for claim in answer.claims:
        require_known(
            set(claim.depends_on_condition_ids),
            set(conditions_by_id),
            "UNKNOWN_CLAIM_CONDITION",
        )
        for condition_id in claim.depends_on_condition_ids:
            condition = conditions_by_id[condition_id]
            if claim.claim_id not in condition.blocking_claim_ids:
                raise ClassificationContractV2Error(
                    "claimとconditionの依存関係が双方向で一致しません",
                    code="CLAIM_CONDITION_LINK_MISMATCH",
                )
            if not set(claim.facet_ids).intersection(condition.facet_ids):
                raise ClassificationContractV2Error(
                    "claimとconditionのfacetが一致しません",
                    code="CLAIM_CONDITION_FACET_MISMATCH",
                )
    for condition in answer.missing_conditions:
        require_known(
            set(condition.blocking_claim_ids),
            set(claims_by_id),
            "UNKNOWN_BLOCKING_CLAIM",
        )
        for claim_id in condition.blocking_claim_ids:
            claim = claims_by_id[claim_id]
            if condition.condition_id not in claim.depends_on_condition_ids:
                raise ClassificationContractV2Error(
                    "conditionとclaimの依存関係が双方向で一致しません",
                    code="CLAIM_CONDITION_LINK_MISMATCH",
                )
            if not set(condition.facet_ids).intersection(claim.facet_ids):
                raise ClassificationContractV2Error(
                    "conditionとclaimのfacetが一致しません",
                    code="CLAIM_CONDITION_FACET_MISMATCH",
                )

    for calculation in answer.date_calculations:
        require_known(
            set(calculation.facet_ids), facet_ids, "UNKNOWN_CALCULATION_FACET"
        )
        require_known(
            set(calculation.evidence_element_ids),
            retrieved_element_ids,
            "UNKNOWN_EVIDENCE",
        )

    assessment_ids = [row.facet_id for row in classification.facet_assessments]
    if len(assessment_ids) != len(set(assessment_ids)):
        raise ClassificationContractV2Error(
            "同じfacetが複数回評価されています", code="DUPLICATE_FACET_ASSESSMENT"
        )
    if set(assessment_ids) != facet_ids:
        raise ClassificationContractV2Error(
            "全requested facetを一度ずつ評価していません",
            code="FACET_ASSESSMENT_MISMATCH",
        )

    review_ids: set[str] = set()
    assessed_claim_ids: set[str] = set()
    for assessment in classification.facet_assessments:
        require_known(set(assessment.claim_ids), set(claims_by_id), "UNKNOWN_CLAIM")
        require_known(
            set(assessment.evidence_element_ids),
            retrieved_element_ids,
            "UNKNOWN_EVIDENCE",
        )
        assessed_claim_ids.update(assessment.claim_ids)
        if assessment.claim_support == "no_claim" and assessment.claim_ids:
            raise ClassificationContractV2Error(
                "no_claimのfacetにclaim参照があります", code="NO_CLAIM_WITH_REFERENCE"
            )
        if assessment.claim_support != "no_claim" and not assessment.claim_ids:
            raise ClassificationContractV2Error(
                "claim評価にclaim参照がありません", code="CLAIM_SUPPORT_WITHOUT_CLAIM"
            )
        if any(
            assessment.facet_id not in claims_by_id[claim_id].facet_ids
            for claim_id in assessment.claim_ids
        ):
            raise ClassificationContractV2Error(
                "assessmentのclaimが対象facetへ割り当てられていません",
                code="CLAIM_FACET_MISMATCH",
            )
        if (
            assessment.evidence_coverage == "insufficient"
            and assessment.human_review_requirements
        ):
            raise ClassificationContractV2Error(
                "文書不足facetに人による確認要件を設定できません",
                code="REVIEW_WITHOUT_DECISION_BASIS",
            )
        if (
            assessment.claim_support == "fully_supported"
            and not assessment.evidence_element_ids
        ):
            raise ClassificationContractV2Error(
                "完全支持されたfacetに根拠参照がありません",
                code="SUPPORTED_WITHOUT_EVIDENCE",
            )
        for review in assessment.human_review_requirements:
            if review.review_id in review_ids:
                raise ClassificationContractV2Error(
                    "review IDが重複しています", code="DUPLICATE_REVIEW_ID"
                )
            review_ids.add(review.review_id)
            require_known(
                set(review.condition_ids), set(conditions_by_id), "UNKNOWN_CONDITION"
            )
            if not review.condition_ids:
                raise ClassificationContractV2Error(
                    "reviewに対応するconditionがありません",
                    code="REVIEW_WITHOUT_CONDITION",
                )
            if any(
                conditions_by_id[condition_id].condition_type != review.requirement_type
                for condition_id in review.condition_ids
            ):
                raise ClassificationContractV2Error(
                    "reviewとconditionのtypeが一致しません",
                    code="REVIEW_CONDITION_TYPE_MISMATCH",
                )
            if any(
                assessment.facet_id not in conditions_by_id[condition_id].facet_ids
                for condition_id in review.condition_ids
            ):
                raise ClassificationContractV2Error(
                    "reviewのconditionが対象facetへ割り当てられていません",
                    code="CONDITION_FACET_MISMATCH",
                )
            require_known(
                set(review.evidence_element_ids),
                retrieved_element_ids,
                "UNKNOWN_EVIDENCE",
            )

    if assessed_claim_ids != set(claims_by_id):
        raise ClassificationContractV2Error(
            "すべてのclaimを少なくとも一つのfacetで評価していません",
            code="UNASSESSED_CLAIM",
        )


def derive_label_v2(classification: ClassificationResultV2) -> ClassificationDecisionV2:
    assessments = classification.facet_assessments
    if any(row.evidence_coverage == "insufficient" for row in assessments):
        return ClassificationDecisionV2("SUCCESS", ANSWER_TYPE_INSUFFICIENT)
    if any(row.claim_support != "fully_supported" for row in assessments):
        return ClassificationDecisionV2(
            "GENERATION_INCOMPLETE", None, "CLAIM_SUPPORT_INCOMPLETE"
        )
    if any(row.human_review_requirements for row in assessments):
        return ClassificationDecisionV2("SUCCESS", ANSWER_TYPE_NEEDS_JUDGMENT)
    return ClassificationDecisionV2("SUCCESS", ANSWER_TYPE_SUFFICIENT)


def decide_classification_v2(
    contract: QuestionContractV2,
    answer: StructuredAnswerV3,
    classification: ClassificationResultV2,
    retrieved_element_ids: set[UUID],
) -> ClassificationDecisionV2:
    try:
        validate_classification_contract_v2(
            contract, answer, classification, retrieved_element_ids
        )
    except ClassificationContractV2Error as exc:
        return ClassificationDecisionV2("PIPELINE_INCONSISTENCY", None, exc.code)
    review_condition_ids = {
        condition_id
        for assessment in classification.facet_assessments
        for review in assessment.human_review_requirements
        for condition_id in review.condition_ids
    }
    if any(
        condition.condition_id not in review_condition_ids
        for condition in answer.missing_conditions
    ):
        return ClassificationDecisionV2(
            "PIPELINE_INCONSISTENCY", None, "UNCLASSIFIED_MISSING_CONDITION"
        )
    return derive_label_v2(classification)


def render_display_answer_v2(
    answer: StructuredAnswerV3,
    classification: ClassificationResultV2,
    decision: ClassificationDecisionV2,
) -> DisplayAnswerV2:
    if decision.status == "PIPELINE_INCONSISTENCY":
        condition_text = "、".join(item.description for item in answer.missing_conditions)
        text = "回答処理の整合性を確認できませんでした。"
        if condition_text:
            text += "\n確認が必要です: " + condition_text
        return DisplayAnswerV2(None, text, (), decision.status, decision.invariant_code)
    if decision.status == "GENERATION_INCOMPLETE":
        return DisplayAnswerV2(None, "必要な回答項目を根拠付きで生成できませんでした。", (), decision.status, decision.invariant_code)

    assessments = {row.facet_id: row for row in classification.facet_assessments}
    blocked_facets = {
        facet_id for facet_id, row in assessments.items()
        if row.human_review_requirements or row.evidence_coverage == "insufficient"
    }
    blocked_facets.update(
        facet_id for condition in answer.missing_conditions
        for facet_id in condition.facet_ids
    )
    unsupported_facets = {
        facet_id for facet_id, row in assessments.items()
        if row.claim_support != "fully_supported"
    }
    conditions_by_facet = {
        facet_id: {condition.condition_id for condition in answer.missing_conditions
                   if facet_id in condition.facet_ids}
        for facet_id in assessments
    }
    visible_claims = []
    suppressed_claims = []
    for claim in answer.claims:
        facets = set(claim.facet_ids)
        unresolved = any(
            condition_id in conditions_by_facet[facet_id]
            for facet_id in facets
            for condition_id in claim.depends_on_condition_ids
        )
        unsupported = bool(facets & unsupported_facets)
        individual_claim = claim.claim_type in {
            "case_fact", "case_outcome", "action_recommendation"
        }
        blocked_individual = individual_claim and bool(facets & blocked_facets)
        if unresolved or unsupported or blocked_individual:
            suppressed_claims.append(claim)
        else:
            visible_claims.append(claim)

    reasons = list(dict.fromkeys(
        [condition.description for condition in answer.missing_conditions]
        + [
            review.description
            for assessment in classification.facet_assessments
            for review in assessment.human_review_requirements
        ]
    ))
    if any(row.evidence_coverage == "insufficient" for row in assessments.values()) and not reasons:
        reasons.append("回答に必要な規則・事実を提示根拠から確認できません")

    lines = [f"回答分類: {decision.label}"]
    if visible_claims:
        lines.extend(["", "回答:"])
        lines.extend(f"- {claim.text}" for claim in visible_claims)
    if reasons:
        lines.extend(["", "確認が必要です: " + "、".join(reasons)])
    elif not visible_claims:
        lines.extend(["", "今回取得した根拠では回答を確認できませんでした。"])
    if suppressed_claims:
        lines.extend(["", "未確定条件に関わる個別結論・処理推奨は表示していません。"])
    if not visible_claims and decision.label == ANSWER_TYPE_SUFFICIENT:
        return DisplayAnswerV2(None, "回答処理の整合性を確認できませんでした。", (), "PIPELINE_INCONSISTENCY", "NO_DISPLAYABLE_CLAIMS")
    return DisplayAnswerV2(decision.label, "\n".join(lines), tuple(visible_claims), "SUCCESS")
