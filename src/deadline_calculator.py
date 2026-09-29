"""Deterministic calendar-day calculations requested by structured answers."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time, timedelta
from uuid import UUID

from src.answering import (
    AnswerClaim,
    DateCalculation,
    MissingCondition,
    StructuredAnswer,
)


COUNTING_RULE_EVIDENCE_MARKERS = {
    "next_day_is_day_1": ("翌日を1日目", "翌日から数え"),
    "anchor_day_is_day_1": ("当日を1日目", "当日から数え"),
}
MISSING_COUNTING_RULE_DESCRIPTION = "期限日を確定するための起算規則"


def calculate_deadline(calculation: DateCalculation) -> tuple[date, time | None]:
    """Calculate only the bounded calendar-day rules supported by answer-output-v2."""
    if calculation.offset_unit != "calendar_day":
        raise ValueError(f"未対応の日付単位です: {calculation.offset_unit}")
    if calculation.offset_value < 1 or calculation.offset_value > 3660:
        raise ValueError("日付offsetは1から3660の範囲である必要があります")
    if calculation.counting_rule == "next_day_is_day_1":
        days = calculation.offset_value
    elif calculation.counting_rule == "anchor_day_is_day_1":
        days = calculation.offset_value - 1
    else:
        raise ValueError(f"未対応の起算規則です: {calculation.counting_rule}")
    return calculation.anchor_date + timedelta(days=days), calculation.cutoff_time


def require_explicit_counting_rule(
    answer: StructuredAnswer,
    evidence_content_by_id: dict[UUID, str],
) -> StructuredAnswer:
    """Drop calculations whose cited evidence does not state the counting rule."""

    supported = []
    unsupported = []
    for calculation in answer.date_calculations:
        evidence = "\n".join(
            evidence_content_by_id.get(element_id, "")
            for element_id in calculation.evidence_element_ids
        )
        markers = COUNTING_RULE_EVIDENCE_MARKERS[calculation.counting_rule]
        if any(marker in evidence for marker in markers):
            supported.append(calculation)
        else:
            unsupported.append(calculation)
    if not unsupported:
        return answer

    missing = list(answer.missing_conditions)
    if not any(
        item.description == MISSING_COUNTING_RULE_DESCRIPTION for item in missing
    ):
        missing.append(
            MissingCondition(
                condition_type="policy_judgment",
                description=MISSING_COUNTING_RULE_DESCRIPTION,
                evidence_element_ids=tuple(
                    dict.fromkeys(
                        element_id
                        for calculation in unsupported
                        for element_id in calculation.evidence_element_ids
                    )
                ),
            )
        )
    return replace(
        answer,
        missing_conditions=tuple(missing),
        date_calculations=tuple(supported),
    )


def _format_deadline(value: date, cutoff: time | None) -> str:
    rendered = f"{value.year}年{value.month}月{value.day}日"
    if cutoff is None:
        return rendered
    local_cutoff = cutoff.replace(tzinfo=None)
    if local_cutoff == time(12, 0):
        return f"{rendered}正午"
    if local_cutoff.second:
        return (
            f"{rendered}{local_cutoff.hour}時{local_cutoff.minute:02d}分"
            f"{local_cutoff.second:02d}秒"
        )
    return f"{rendered}{local_cutoff.hour}時{local_cutoff.minute:02d}分"


def apply_date_calculations(answer: StructuredAnswer) -> StructuredAnswer:
    """Append deterministic derived claims while preserving the model's raw claims."""
    claims = list(answer.claims)
    for calculation in answer.date_calculations:
        value, cutoff = calculate_deadline(calculation)
        ordinal = len(claims) + 1
        claims.append(
            AnswerClaim(
                claim_id=f"claim-{ordinal}",
                ordinal=ordinal,
                text=(
                    f"{calculation.result_label}は"
                    f"{_format_deadline(value, cutoff)}です。"
                ),
                evidence_element_ids=calculation.evidence_element_ids,
                evidence_kind="text",
            )
        )
    return replace(answer, claims=tuple(claims))
