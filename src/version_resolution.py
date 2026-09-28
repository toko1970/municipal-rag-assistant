"""Parse and validate the dedicated document-version resolution contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


RESOLUTION_BASES = {
    "question_date",
    "effective_period",
    "precedence_rule",
    "single_applicable_source",
    "unresolved",
}


@dataclass(frozen=True)
class VersionResolution:
    version_conflict: bool
    resolution_basis: str
    evidence_element_ids: tuple[UUID, ...]
    confidence: float


def parse_version_resolution(data: dict[str, Any]) -> VersionResolution:
    required = {
        "schema_version",
        "status",
        "version_conflict",
        "resolution_basis",
        "evidence_element_ids",
        "confidence",
        "error_code",
    }
    if set(data) != required or data["schema_version"] != "1.0":
        raise ValueError("版解決出力がschemaと一致しません")
    if data["status"] != "SUCCESS":
        raise ValueError(str(data.get("error_code") or "RESOLUTION_FAILED"))
    if type(data["version_conflict"]) is not bool:
        raise ValueError("version_conflictはbooleanである必要があります")
    basis = data["resolution_basis"]
    if basis not in RESOLUTION_BASES:
        raise ValueError("未対応のresolution_basisです")
    if data["version_conflict"] != (basis == "unresolved"):
        raise ValueError("version_conflictとresolution_basisが矛盾しています")
    raw_ids = data["evidence_element_ids"]
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("版解決には1件以上の根拠IDが必要です")
    try:
        evidence_ids = tuple(UUID(value) for value in raw_ids)
    except (TypeError, ValueError) as exc:
        raise ValueError("版解決の根拠IDはUUIDである必要があります") from exc
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("版解決の根拠IDが重複しています")
    confidence = data["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("confidenceは数値である必要があります")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("confidenceは0から1の範囲である必要があります")
    if data["error_code"] is not None:
        raise ValueError("成功した版解決にerror_codeは設定できません")
    return VersionResolution(
        version_conflict=data["version_conflict"],
        resolution_basis=basis,
        evidence_element_ids=evidence_ids,
        confidence=float(confidence),
    )
