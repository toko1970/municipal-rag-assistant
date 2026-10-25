"""Cross-reference validation and deterministic decisions for contract v2."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from config import (
    ANSWER_TYPE_INSUFFICIENT,
    ANSWER_TYPE_NEEDS_JUDGMENT,
    ANSWER_TYPE_SUFFICIENT,
)
from src.classification_contract_v2_types import (
    AnswerClaimV3 as AnswerClaimV3,
    ClassificationContractV2Error as ClassificationContractV2Error,
    ClassificationDecisionV2 as ClassificationDecisionV2,
    ClassificationResultV2 as ClassificationResultV2,
    DateCalculationV3 as DateCalculationV3,
    DisplayAnswerV2 as DisplayAnswerV2,
    FacetAssessmentV2 as FacetAssessmentV2,
    HumanReviewRequirementV2 as HumanReviewRequirementV2,
    InputFactV2 as InputFactV2,
    MissingConditionV3 as MissingConditionV3,
    QuestionContractV2 as QuestionContractV2,
    QuestionFacetV2 as QuestionFacetV2,
    StructuredAnswerV3 as StructuredAnswerV3,
)
from src.classification_display_v2 import (
    render_display_answer_v2 as render_display_answer_v2,
)
from src.classification_parsing_v2 import (
    parse_answer_output_v3 as parse_answer_output_v3,
    parse_classification_output_v2 as parse_classification_output_v2,
    parse_question_contract_v2 as parse_question_contract_v2,
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
