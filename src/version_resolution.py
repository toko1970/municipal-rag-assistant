"""Parse and validate the dedicated document-version resolution contract."""

from __future__ import annotations

from dataclasses import dataclass
import json
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


def build_version_resolution_prompt(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    payload = json.dumps(
        {
            "question": question,
            "retrieved_evidence": evidence,
            "generated_answer": answer_data,
        },
        ensure_ascii=False,
    )
    return (
        "version-resolution-v1のJSONだけを返してください。回答全体の十分性、個別事情、"
        "制度解釈は判定せず、質問へ適用する文書版が一意に決まるかだけを判定します。\n"
        "- 質問の基準日、根拠の施行日・適用期間、明示された優先規則の順に確認します。\n"
        "- それらから適用版を一意に決められる場合はversion_conflict=falseです。"
        "resolution_basisは実際に解決へ使った根拠を選びます。\n"
        "- 複数版が取得された事実だけでは競合にしません。\n"
        "- 質問の結論に関係する根拠が一つだけで、他の取得根拠が無関係なら"
        "version_conflict=false、resolution_basis=single_applicable_sourceです。\n"
        "- 結論に関係する複数版を上記情報で選べない場合だけversion_conflict=true、"
        "resolution_basis=unresolvedです。\n"
        "- evidence_element_idsには判定に使った取得根拠のelement_idだけを入れます。\n"
        f"判定対象: {payload}"
    )


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
