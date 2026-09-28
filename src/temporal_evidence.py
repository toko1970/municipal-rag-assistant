"""Deterministic pre-generation guidance for dated policy evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from src.contracts import SearchHit


POLICY_DOMAINS = ("通勤手当", "住居手当", "扶養手当")
QUESTION_DOMAIN_ALIASES = {
    "出生": "扶養手当",
}


@dataclass(frozen=True)
class TemporalPolicyGuidance:
    question_date: date | None
    comparison_requested: bool
    applicable_domains: tuple[str, ...]
    applicable_revision_element_ids: tuple[str, ...]
    older_conflicting_element_ids: tuple[str, ...]


def extract_question_date(question: str) -> date | None:
    match = re.search(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?", question)
    if match is None:
        return None
    return date(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 1),
    )


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _text(hit: SearchHit) -> str:
    metadata = hit.element.metadata
    headings = " ".join(
        str(metadata.get(key, "")) for key in ("見出し1", "見出し2", "見出し3")
    )
    return f"{headings} {hit.element.content}"


def _domains(hit: SearchHit) -> set[str]:
    text = _text(hit)
    return {domain for domain in POLICY_DOMAINS if domain in text}


def _question_domains(question: str) -> set[str]:
    domains = {domain for domain in POLICY_DOMAINS if domain in question}
    domains.update(
        domain
        for phrase, domain in QUESTION_DOMAIN_ALIASES.items()
        if phrase in question
    )
    return domains


def analyze_temporal_evidence(
    question: str, hits: list[SearchHit]
) -> TemporalPolicyGuidance | None:
    question_date = extract_question_date(question)
    comparison_requested = "改正前後" in question or "どう変わ" in question
    if question_date is None and not comparison_requested:
        return None
    question_domains = _question_domains(question)
    if not question_domains:
        return None

    revision_hits = [
        hit
        for hit in hits
        if hit.element.metadata.get("document_role") == "revision_history"
        and _domains(hit).intersection(question_domains)
    ]
    if not revision_hits:
        return None

    if comparison_requested:
        domains = sorted(
            set()
            .union(*(_domains(hit) for hit in revision_hits))
            .intersection(question_domains)
        )
        return TemporalPolicyGuidance(
            question_date=question_date,
            comparison_requested=True,
            applicable_domains=tuple(domains),
            applicable_revision_element_ids=tuple(
                str(hit.element.id) for hit in revision_hits
            ),
            older_conflicting_element_ids=(),
        )

    applicable = [
        hit
        for hit in revision_hits
        if (effective := _parse_date(hit.element.metadata.get("effective_date")))
        and effective <= question_date
        and str(hit.element.metadata.get("見出し2", "")) in {"改正後", "経過措置"}
    ]
    if not applicable:
        return None
    domains = sorted(
        set()
        .union(*(_domains(hit) for hit in applicable))
        .intersection(question_domains)
    )
    latest_effective = max(
        _parse_date(hit.element.metadata["effective_date"]) for hit in applicable
    )
    older_conflicting = [
        hit
        for hit in hits
        if hit not in applicable
        and _domains(hit).intersection(domains)
        and hit.element.metadata.get("document_role") != "revision_history"
        and (effective := _parse_date(hit.element.metadata.get("effective_date")))
        and effective < latest_effective
    ]
    return TemporalPolicyGuidance(
        question_date=question_date,
        comparison_requested=False,
        applicable_domains=tuple(domains),
        applicable_revision_element_ids=tuple(
            str(hit.element.id) for hit in applicable
        ),
        older_conflicting_element_ids=tuple(
            str(hit.element.id) for hit in older_conflicting
        ),
    )


def temporal_prompt_instruction(question: str, hits: list[SearchHit]) -> str | None:
    guidance = analyze_temporal_evidence(question, hits)
    if guidance is None:
        return None
    domains = "、".join(guidance.applicable_domains)
    revision_ids = "、".join(guidance.applicable_revision_element_ids)
    if guidance.comparison_requested:
        return (
            f"版適用情報: {domains}の改正前後を比較する質問です。"
            f"改正通知の両方の記載を保持してください。対象element_id: {revision_ids}"
        )
    older_ids = "、".join(guidance.older_conflicting_element_ids) or "なし"
    return (
        f"版適用情報: 質問基準日は{guidance.question_date.isoformat()}です。"
        f"{domains}については、適用済み改正通知の改正後・経過措置を優先してください。"
        f"優先element_id: {revision_ids}。旧記載候補element_id: {older_ids}。"
        "旧記載候補が優先根拠と矛盾する場合は採用しないでください。"
        "改正対象と異なる届出期限などの補完根拠はそのまま使用してください。"
    )
