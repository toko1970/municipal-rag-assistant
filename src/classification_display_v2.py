"""Display rendering for validated facet classification results."""

from __future__ import annotations

from config import ANSWER_TYPE_SUFFICIENT
from src.classification_contract_v2_types import (
    ClassificationDecisionV2,
    ClassificationResultV2,
    DisplayAnswerV2,
    StructuredAnswerV3,
)


def render_display_answer_v2(
    answer: StructuredAnswerV3,
    classification: ClassificationResultV2,
    decision: ClassificationDecisionV2,
) -> DisplayAnswerV2:
    if decision.status == "PIPELINE_INCONSISTENCY":
        condition_text = "、".join(
            item.description for item in answer.missing_conditions
        )
        text = "回答処理の整合性を確認できませんでした。"
        if condition_text:
            text += "\n確認が必要です: " + condition_text
        return DisplayAnswerV2(None, text, (), decision.status, decision.invariant_code)
    if decision.status == "GENERATION_INCOMPLETE":
        return DisplayAnswerV2(
            None,
            "必要な回答項目を根拠付きで生成できませんでした。",
            (),
            decision.status,
            decision.invariant_code,
        )

    assessments = {row.facet_id: row for row in classification.facet_assessments}
    blocked_facets = {
        facet_id
        for facet_id, row in assessments.items()
        if row.human_review_requirements or row.evidence_coverage == "insufficient"
    }
    blocked_facets.update(
        facet_id
        for condition in answer.missing_conditions
        for facet_id in condition.facet_ids
    )
    unsupported_facets = {
        facet_id
        for facet_id, row in assessments.items()
        if row.claim_support != "fully_supported"
    }
    conditions_by_facet = {
        facet_id: {
            condition.condition_id
            for condition in answer.missing_conditions
            if facet_id in condition.facet_ids
        }
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
            "case_fact",
            "case_outcome",
            "action_recommendation",
        }
        blocked_individual = individual_claim and bool(facets & blocked_facets)
        if unresolved or unsupported or blocked_individual:
            suppressed_claims.append(claim)
        else:
            visible_claims.append(claim)

    reasons = list(
        dict.fromkeys(
            [condition.description for condition in answer.missing_conditions]
            + [
                review.description
                for assessment in classification.facet_assessments
                for review in assessment.human_review_requirements
            ]
        )
    )
    if (
        any(row.evidence_coverage == "insufficient" for row in assessments.values())
        and not reasons
    ):
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
        return DisplayAnswerV2(
            None,
            "回答処理の整合性を確認できませんでした。",
            (),
            "PIPELINE_INCONSISTENCY",
            "NO_DISPLAYABLE_CLAIMS",
        )
    return DisplayAnswerV2(
        decision.label, "\n".join(lines), tuple(visible_claims), "SUCCESS"
    )
