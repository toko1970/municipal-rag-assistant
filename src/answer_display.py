"""Rendering safe user-facing answers from validated answer decisions."""

from __future__ import annotations

from dataclasses import dataclass

from config import ANSWER_TYPE_INSUFFICIENT, ANSWER_TYPE_NEEDS_JUDGMENT, ANSWER_TYPE_SUFFICIENT
from src.answer_classification import ClassificationResult, derive_label
from src.answer_contract import AnswerClaim, StructuredAnswer


@dataclass(frozen=True)
class DisplayAnswer:
    label: str | None
    text: str
    visible_claims: tuple[AnswerClaim, ...]
    status: str = "SUCCESS"
    invariant_code: str | None = None


class DisplayContractError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def render_display_answer(
    answer: StructuredAnswer, classification: ClassificationResult
) -> DisplayAnswer:
    factors = classification.factors
    label = derive_label(factors)
    if label == ANSWER_TYPE_SUFFICIENT:
        if not answer.claims:
            raise DisplayContractError(
                "根拠十分なのにclaimがありません",
                code="SUFFICIENT_WITHOUT_CLAIMS",
            )
        if answer.missing_conditions:
            raise DisplayContractError(
                "根拠十分なのに未解決条件が残っています",
                code="SUFFICIENT_WITH_MISSING_CONDITIONS",
            )
        visible_claims = answer.claims
        guidance = ""
    elif label == ANSWER_TYPE_NEEDS_JUDGMENT:
        visible_claims = answer.claims if factors.answer_fully_supported else ()
        reasons = [item.description for item in answer.missing_conditions]
        if factors.requires_case_facts:
            reasons.append("個別事情の確認")
        if factors.requires_policy_judgment:
            reasons.append("制度所管部署による解釈")
        if factors.version_conflict:
            reasons.append("適用する文書版の確認")
        unique_reasons = list(dict.fromkeys(reasons))
        guidance = "確認が必要です: " + "、".join(unique_reasons)
    else:
        visible_claims = ()
        guidance = "今回取得した根拠では回答を確認できませんでした。"

    lines = [f"回答分類: {label}"]
    if visible_claims:
        lines.extend(["", "回答:"])
        lines.extend(f"- {claim.text}" for claim in visible_claims)
    if guidance:
        lines.extend(["", guidance])
    return DisplayAnswer(
        label=label, text="\n".join(lines), visible_claims=visible_claims
    )


def render_pipeline_inconsistency(
    answer: StructuredAnswer,
    classification: ClassificationResult,
    error: DisplayContractError,
) -> DisplayAnswer:
    """Return a safe response while preserving the inconsistency for evaluation."""
    condition_types = {
        condition.condition_type for condition in answer.missing_conditions
    }
    if condition_types and condition_types <= {"missing_document"}:
        label = ANSWER_TYPE_INSUFFICIENT
        guidance = "今回取得した根拠では回答を確認できませんでした。"
        visible_claims: tuple[AnswerClaim, ...] = ()
    else:
        label = ANSWER_TYPE_NEEDS_JUDGMENT
        visible_claims = (
            answer.claims if classification.factors.answer_fully_supported else ()
        )
        reasons = [item.description for item in answer.missing_conditions]
        guidance = "確認が必要です"
        if reasons:
            guidance += ": " + "、".join(dict.fromkeys(reasons))
        else:
            guidance += ": 回答処理内の判定が整合しませんでした"

    lines = [f"回答分類: {label}"]
    if visible_claims:
        lines.extend(["", "回答:"])
        lines.extend(f"- {claim.text}" for claim in visible_claims)
    lines.extend(["", guidance])
    return DisplayAnswer(
        label=label,
        text="\n".join(lines),
        visible_claims=visible_claims,
        status="PIPELINE_INCONSISTENCY",
        invariant_code=error.code,
    )
