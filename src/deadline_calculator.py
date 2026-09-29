"""Deterministic calendar-day calculations requested by structured answers."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time, timedelta

from src.answering import AnswerClaim, DateCalculation, StructuredAnswer


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
