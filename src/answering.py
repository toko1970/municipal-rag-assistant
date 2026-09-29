"""Structured answer validation, classification mapping, and display rendering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
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
class MissingCondition:
    condition_type: str
    description: str
    evidence_element_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class DateCalculation:
    calculation_id: str
    result_label: str
    anchor_date: date
    offset_value: int
    offset_unit: str
    counting_rule: str
    cutoff_time: time | None
    evidence_element_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class StructuredAnswer:
    claims: tuple[AnswerClaim, ...]
    missing_conditions: tuple[MissingCondition, ...]
    date_calculations: tuple[DateCalculation, ...] = ()


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
    status: str = "SUCCESS"
    invariant_code: str | None = None


class DisplayContractError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


MISSING_CONDITION_TYPES = {
    "case_fact",
    "policy_judgment",
    "missing_document",
    "version_conflict",
}


def _uuid_tuple(values: Any, *, field: str, allow_empty: bool) -> tuple[UUID, ...]:
    if not isinstance(values, list) or (not allow_empty and not values):
        qualifier = "配列" if allow_empty else "1件以上の配列"
        raise ValueError(f"{field}は{qualifier}である必要があります")
    try:
        parsed = tuple(UUID(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}はUUIDである必要があります") from exc
    if len(parsed) != len(set(parsed)):
        raise ValueError(f"{field}が重複しています")
    return parsed


def _parse_missing_conditions(
    raw_missing: Any, *, schema_version: str
) -> tuple[MissingCondition, ...]:
    if not isinstance(raw_missing, list):
        raise ValueError("missing_conditionsは配列である必要があります")
    if schema_version == "1.0":
        if not all(isinstance(item, str) and item.strip() for item in raw_missing):
            raise ValueError("missing_conditionsは空でない文字列だけを許可します")
        descriptions = [item.strip() for item in raw_missing]
        if len(descriptions) != len(set(descriptions)):
            raise ValueError("missing_conditionsが重複しています")
        return tuple(
            MissingCondition("unspecified", description, ())
            for description in descriptions
        )

    result = []
    for raw in raw_missing:
        required = {"type", "description", "evidence_element_ids"}
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("missing condition項目がschemaと一致しません")
        condition_type = raw["type"]
        if condition_type not in MISSING_CONDITION_TYPES:
            raise ValueError("未対応のmissing condition typeです")
        description = raw["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError("missing condition descriptionは空にできません")
        result.append(
            MissingCondition(
                condition_type=condition_type,
                description=description.strip(),
                evidence_element_ids=_uuid_tuple(
                    raw["evidence_element_ids"],
                    field="missing condition evidence_element_ids",
                    allow_empty=True,
                ),
            )
        )
    identity = [(item.condition_type, item.description) for item in result]
    if len(identity) != len(set(identity)):
        raise ValueError("missing_conditionsが重複しています")
    return tuple(result)


def _parse_date_calculations(raw_calculations: Any) -> tuple[DateCalculation, ...]:
    if not isinstance(raw_calculations, list):
        raise ValueError("date_calculationsは配列である必要があります")
    result = []
    for raw in raw_calculations:
        required = {
            "calculation_id",
            "result_label",
            "anchor_date",
            "offset_value",
            "offset_unit",
            "counting_rule",
            "cutoff_time",
            "evidence_element_ids",
        }
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("date calculation項目がschemaと一致しません")
        calculation_id = raw["calculation_id"]
        if calculation_id != f"date-{len(result) + 1}":
            raise ValueError("date calculation IDはdate-1から連続させてください")
        label = raw["result_label"]
        if not isinstance(label, str) or not label.strip():
            raise ValueError("date calculation result_labelは空にできません")
        try:
            anchor = date.fromisoformat(raw["anchor_date"])
            cutoff = (
                time.fromisoformat(raw["cutoff_time"])
                if raw["cutoff_time"] is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("日付または時刻がISO形式ではありません") from exc
        offset = raw["offset_value"]
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or not 1 <= offset <= 3660
        ):
            raise ValueError("date calculation offsetは1から3660の整数です")
        if raw["offset_unit"] != "calendar_day":
            raise ValueError("初期scopeではcalendar_dayだけを許可します")
        if raw["counting_rule"] not in {
            "next_day_is_day_1",
            "anchor_day_is_day_1",
        }:
            raise ValueError("未対応の起算規則です")
        result.append(
            DateCalculation(
                calculation_id=calculation_id,
                result_label=label.strip(),
                anchor_date=anchor,
                offset_value=offset,
                offset_unit=raw["offset_unit"],
                counting_rule=raw["counting_rule"],
                cutoff_time=cutoff,
                evidence_element_ids=_uuid_tuple(
                    raw["evidence_element_ids"],
                    field="date calculation evidence_element_ids",
                    allow_empty=False,
                ),
            )
        )
    return tuple(result)


def parse_answer_output(data: dict[str, Any]) -> StructuredAnswer:
    schema_version = data.get("schema_version")
    expected = (
        {"schema_version", "claims", "missing_conditions"}
        if schema_version == "1.0"
        else {
            "schema_version",
            "claims",
            "missing_conditions",
            "date_calculations",
        }
    )
    if set(data) != expected:
        raise ValueError("回答出力のtop-level項目がschemaと一致しません")
    if schema_version not in {"1.0", "2.0"}:
        raise ValueError("未対応の回答schema versionです")
    raw_claims = data["claims"]
    raw_missing = data["missing_conditions"]
    if not isinstance(raw_claims, list):
        raise ValueError("claimsは配列である必要があります")

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
        parsed_ids = _uuid_tuple(
            raw["evidence_element_ids"],
            field="claim evidence_element_ids",
            allow_empty=False,
        )
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
    return StructuredAnswer(
        tuple(claims),
        _parse_missing_conditions(raw_missing, schema_version=schema_version),
        _parse_date_calculations(data["date_calculations"])
        if schema_version == "2.0"
        else (),
    )


def validate_answer_evidence(
    answer: StructuredAnswer, retrieved_element_ids: set[UUID]
) -> None:
    cited = {
        evidence_id
        for claim in answer.claims
        for evidence_id in claim.evidence_element_ids
    }
    cited.update(
        evidence_id
        for condition in answer.missing_conditions
        for evidence_id in condition.evidence_element_ids
    )
    cited.update(
        evidence_id
        for calculation in answer.date_calculations
        for evidence_id in calculation.evidence_element_ids
    )
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
    if (
        factors.version_conflict
        or factors.requires_case_facts
        or factors.requires_policy_judgment
    ):
        return ANSWER_TYPE_NEEDS_JUDGMENT
    if not factors.retrieval_sufficient or not factors.answer_fully_supported:
        return ANSWER_TYPE_INSUFFICIENT
    return ANSWER_TYPE_SUFFICIENT


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
