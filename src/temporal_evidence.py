"""Deterministic pre-generation guidance for dated policy evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from src.contracts import SearchHit
from src.query_service import build_generation_prompt


POLICY_DOMAINS = ("通勤手当", "住居手当", "扶養手当")
QUESTION_DOMAIN_ALIASES = {
    "出生": "扶養手当",
}
TEMPORAL_GENERATION_PROMPT_VERSION = "answer-claims-v1+temporal-guidance-v1"
ANSWER_CONTRACT_V2_PROMPT_VERSION = "answer-contract-v2.2+deadline-calculation-v1"
DEADLINE_CALCULATION_PROMPT_VERSION = "answer-claims-v1.1+deadline-calculation-v1"


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
    if "家賃" in question and any(
        phrase in question for phrase in ("入居", "住宅", "賃貸")
    ):
        domains.add("住居手当")
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


def build_temporal_generation_prompt(
    question: str, hits: list[SearchHit], visual_assets: object
) -> str:
    base = build_generation_prompt(question, hits, visual_assets)
    instruction = temporal_prompt_instruction(question, hits)
    return f"{instruction}\n{base}" if instruction else base


def build_answer_contract_v2_prompt(
    question: str, hits: list[SearchHit], visual_assets: object
) -> str:
    base = build_temporal_generation_prompt(question, hits, visual_assets).replace(
        "answer-output-v1", "answer-output-v2"
    )
    contract = (
        "answer-output-v2追加規則:\n"
        "- missing_conditionsはtype、description、evidence_element_idsを持つobjectにしてください。\n"
        "- case_factは質問の結論に必要だが質問中にない個別事実、policy_judgmentは必要事実が揃っても"
        "制度所管課の裁量が残る場合、missing_documentは必要文書が取得根拠にない場合です。\n"
        "- version_conflictは必要な基準日が揃っても適用版を一意に決められない場合です。"
        "基準日そのものがない場合はcase_factにしてください。\n"
        "- missing_conditionsへ入れるのは、質問が明示的に求める結論を答えるために必須の未解決条件だけです。"
        "質問が求めていない例外、将来の個別適用、より細かな日付・金額・手続は追加しないでください。\n"
        "- 質問が一般ルール、選択肢、項目一覧を尋ねる場合、取得根拠からその範囲を答えられれば"
        "missing_conditionsは空です。各選択肢を個別事案へ適用するための事情は不足条件にしません。\n"
        "- claimsも質問が明示的に求める対象と範囲へ限定してください。取得根拠に関連制度の記載があっても、"
        "質問と異なる手当・対象者・手続の規則や、結論に不要な周辺情報を追加しないでください。\n"
        "- 質問が『この規程だけで確定・判断できるか』を尋ね、取得根拠が別規程によることを明示する場合、"
        "『この規程だけでは判断できない』という結論は根拠付きで回答済みです。"
        "別規程自体をmissing_documentへ入れないでください。\n"
        "- 質問が具体的な期限日を求め、取得根拠に暦日数と起算規則がある場合だけ、"
        "date_calculationsへ構造化してください。\n"
        "- 対応するのはcalendar_dayと、next_day_is_day_1またはanchor_day_is_day_1だけです。\n"
        "- 営業日、休日、閉庁日など未対応の計算は推測せずmissing_conditionsへ入れてください。\n"
        "- date_calculationsへ入れた具体的な計算結果をclaimsで推測しないでください。"
        "アプリケーションが決定的に計算します。\n"
        "- missing_conditionsとdate_calculationsがない場合も空配列を返してください。"
    )
    return f"{contract}\n{base}"


def should_use_deadline_calculation(question: str) -> bool:
    date_pattern = r"(?:\d{4}年\d{1,2}月\d{1,2}日|\d{4}[/-]\d{1,2}[/-]\d{1,2})"
    if not re.search(date_pattern, question):
        return False

    unsupported_calendar = (
        "営業日",
        "開庁日",
        "閉庁日",
        "休日を除",
        "土日を除",
    )
    if any(phrase in question for phrase in unsupported_calendar):
        return False

    anchor_after_date = re.search(
        rf"{date_pattern}(?:に|から|を起算日|を基準日)", question
    )
    named_anchor_before_date = re.search(
        rf"(?:受験日|申請日|受理日|利用開始日|採用日|届出日|起算日|基準日|発生日)"
        rf"(?:は|が|：|:)\s*{date_pattern}",
        question,
    )
    if not anchor_after_date and not named_anchor_before_date:
        return False

    concrete_deadline_phrases = (
        "期限日",
        "締切日",
        "締め切り日",
        "提出日",
        "提出期日",
        "期限となる日",
        "何日まで",
        "いつまで",
        "具体的な日付",
        "具体的な期限日",
        "暦の上ではいつ",
    )
    return any(phrase in question for phrase in concrete_deadline_phrases)


def build_deadline_calculation_prompt(
    question: str, hits: list[SearchHit], visual_assets: object
) -> str:
    base = build_temporal_generation_prompt(question, hits, visual_assets).replace(
        "answer-output-v1", "answer-output-v1.1"
    )
    rules = (
        "answer-output-v1.1追加規則:\n"
        "- 取得根拠に暦日数と起算規則があり、質問が具体的な期限日を求める場合だけ、"
        "date_calculationsへ構造化してください。\n"
        "- 対応するのはcalendar_dayと、next_day_is_day_1またはanchor_day_is_day_1だけです。\n"
        "- 営業日、休日、閉庁日など未対応の計算は推測せず、従来どおりmissing_conditionsへ"
        "文字列で入れてください。\n"
        "- date_calculationsへ入れた具体的な計算結果をclaimsで推測しないでください。"
        "アプリケーションが決定的に計算します。\n"
        "- date_calculationsがない場合も空配列を返してください。"
    )
    return f"{rules}\n{base}"
