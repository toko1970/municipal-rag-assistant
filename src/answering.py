"""Structured answer validation, classification mapping, and display rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from config import (
    ANSWER_TYPE_INSUFFICIENT,
    ANSWER_TYPE_NEEDS_JUDGMENT,
    ANSWER_TYPE_SUFFICIENT,
)


@dataclass(frozen=True)
class AnswerClaim:
    claim_id: str
    ordinal: int
    text: str
    evidence_element_ids: tuple[UUID, ...]
    evidence_kind: str


@dataclass(frozen=True)
class StructuredAnswer:
    claims: tuple[AnswerClaim, ...]
    missing_conditions: tuple[str, ...]


@dataclass(frozen=True)
class ClassificationFactors:
    retrieval_sufficient: bool
    answer_fully_supported: bool
    requires_case_facts: bool
    requires_policy_judgment: bool
    version_conflict: bool


@dataclass(frozen=True)
class ClassificationResult:
    factors: ClassificationFactors
    confidence: float


@dataclass(frozen=True)
class DisplayAnswer:
    label: str
    text: str
    visible_claims: tuple[AnswerClaim, ...]


def parse_answer_output(data: dict[str, Any]) -> StructuredAnswer:
    if set(data) != {"schema_version", "claims", "missing_conditions"}:
        raise ValueError("回答出力のtop-level項目がschemaと一致しません")
    if data["schema_version"] != "1.0":
        raise ValueError("未対応の回答schema versionです")
    raw_claims = data["claims"]
    raw_missing = data["missing_conditions"]
    if not isinstance(raw_claims, list) or not isinstance(raw_missing, list):
        raise ValueError("claimsとmissing_conditionsは配列である必要があります")

    claims = []
    expected_ordinals = list(range(1, len(raw_claims) + 1))
    for raw in raw_claims:
        required = {
            "claim_id",
            "ordinal",
            "text",
            "evidence_element_ids",
            "evidence_kind",
        }
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("claim項目がschemaと一致しません")
        ordinal = raw["ordinal"]
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise ValueError("claim ordinalは整数である必要があります")
        evidence_ids = raw["evidence_element_ids"]
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ValueError("claimには1件以上の根拠IDが必要です")
        try:
            parsed_ids = tuple(UUID(value) for value in evidence_ids)
        except (TypeError, ValueError) as exc:
            raise ValueError("根拠IDはUUIDである必要があります") from exc
        if len(parsed_ids) != len(set(parsed_ids)):
            raise ValueError("同じclaim内で根拠IDが重複しています")
        claim_id = raw["claim_id"]
        if claim_id != f"claim-{ordinal}":
            raise ValueError("claim_idとordinalが対応していません")
        text = raw["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("claim textは空にできません")
        evidence_kind = raw["evidence_kind"]
        if evidence_kind not in {
            "text",
            "table_cell",
            "flow_edge",
            "form_field",
            "timeline_event",
        }:
            raise ValueError("未対応のevidence_kindです")
        claims.append(
            AnswerClaim(
                claim_id=claim_id,
                ordinal=ordinal,
                text=text.strip(),
                evidence_element_ids=parsed_ids,
                evidence_kind=evidence_kind,
            )
        )

    if [claim.ordinal for claim in claims] != expected_ordinals:
        raise ValueError("claim ordinalは1から連続している必要があります")
    if not all(isinstance(item, str) and item.strip() for item in raw_missing):
        raise ValueError("missing_conditionsは空でない文字列だけを許可します")
    normalized_missing = tuple(item.strip() for item in raw_missing)
    if len(normalized_missing) != len(set(normalized_missing)):
        raise ValueError("missing_conditionsが重複しています")
    return StructuredAnswer(tuple(claims), normalized_missing)


def validate_answer_evidence(
    answer: StructuredAnswer, retrieved_element_ids: set[UUID]
) -> None:
    cited = {
        evidence_id
        for claim in answer.claims
        for evidence_id in claim.evidence_element_ids
    }
    unknown = cited - retrieved_element_ids
    if unknown:
        raise ValueError(
            f"今回取得していない根拠IDが含まれています: {sorted(map(str, unknown))}"
        )


def parse_classification_output(data: dict[str, Any]) -> ClassificationResult:
    required = {"schema_version", "status", "factors", "confidence", "error_code"}
    if set(data) != required or data["schema_version"] != "1.0":
        raise ValueError("分類出力がschemaと一致しません")
    if data["status"] != "SUCCESS":
        raise ValueError(str(data.get("error_code") or "CLASSIFICATION_FAILED"))
    raw = data["factors"]
    factor_keys = {
        "retrieval_sufficient",
        "answer_fully_supported",
        "requires_case_facts",
        "requires_policy_judgment",
        "version_conflict",
    }
    if not isinstance(raw, dict) or set(raw) != factor_keys:
        raise ValueError("分類要因がschemaと一致しません")
    if any(type(raw[key]) is not bool for key in factor_keys):
        raise ValueError("分類要因はbooleanである必要があります")
    confidence = data["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("confidenceは数値である必要があります")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("confidenceは0から1の範囲である必要があります")
    if data["error_code"] is not None:
        raise ValueError("成功した分類にerror_codeは設定できません")
    return ClassificationResult(
        factors=ClassificationFactors(**raw), confidence=float(confidence)
    )


def derive_label(factors: ClassificationFactors) -> str:
    if not factors.retrieval_sufficient:
        return ANSWER_TYPE_INSUFFICIENT
    if (
        factors.version_conflict
        or factors.requires_case_facts
        or factors.requires_policy_judgment
    ):
        return ANSWER_TYPE_NEEDS_JUDGMENT
    if not factors.answer_fully_supported:
        return ANSWER_TYPE_INSUFFICIENT
    return ANSWER_TYPE_SUFFICIENT


def render_display_answer(
    answer: StructuredAnswer, classification: ClassificationResult
) -> DisplayAnswer:
    factors = classification.factors
    label = derive_label(factors)
    if label == ANSWER_TYPE_SUFFICIENT:
        if not answer.claims or answer.missing_conditions:
            raise ValueError("根拠十分の表示条件を満たしていません")
        visible_claims = answer.claims
        guidance = ""
    elif label == ANSWER_TYPE_NEEDS_JUDGMENT:
        visible_claims = answer.claims if factors.answer_fully_supported else ()
        reasons = list(answer.missing_conditions)
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
