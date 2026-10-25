"""Parsing and deterministic mapping for answer classifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import (
    ANSWER_TYPE_INSUFFICIENT,
    ANSWER_TYPE_NEEDS_JUDGMENT,
    ANSWER_TYPE_SUFFICIENT,
)


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
