"""Dependency-injected text RAG v2 query flow."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID

from src.answering import (
    DisplayAnswer,
    DisplayContractError,
    derive_label,
    parse_answer_output,
    parse_classification_output,
    render_display_answer,
    render_pipeline_inconsistency,
    validate_answer_evidence,
)
from src.asset_store import AssetReader, LocalAssetReader, VisualEvidenceAsset
from src.contracts import SearchHit, VectorIndex
from src.deadline_calculator import apply_date_calculations
from src.llm_provider import StructuredLLMProvider, StructuredLLMResult
from src.version_resolution import (
    build_version_resolution_prompt,
    parse_version_resolution,
)


GENERATION_PROMPT_VERSION = "answer-claims-v1"
CLASSIFICATION_PROMPT_VERSION = "answer-classification-v1"
CLASSIFICATION_DECISION_VERSION = "classification-decision-v1"
VERSION_RESOLUTION_PROMPT_VERSION = "version-resolution-v2"
VERSION_RESOLUTION_DECISION_VERSION = "classification-decision-v1+version-resolution-v2"
VERSION_RESOLUTION_CONFIDENCE_THRESHOLD = 0.80


class QueryEventLogger(Protocol):
    def start_request(self, question: str) -> UUID: ...

    def record_retrieval(self, request_id: UUID, hits: list[SearchHit]) -> None: ...

    def record_generation_attempt(self, request_id: UUID, **kwargs) -> UUID: ...

    def record_classification_attempt(self, request_id: UUID, **kwargs) -> UUID: ...

    def record_answer_result(self, request_id: UUID, **kwargs) -> UUID: ...


class MultimodalStructuredLLMProvider(StructuredLLMProvider, Protocol):
    def generate_structured_with_media(
        self,
        prompt: str,
        schema: dict,
        *,
        media: list[tuple[bytes, str]],
    ) -> StructuredLLMResult: ...


def _evidence_payload(
    hits: list[SearchHit],
    visual_assets: dict[UUID, VisualEvidenceAsset] | None = None,
    *,
    display_content: dict[UUID, bytes] | None = None,
) -> list[dict]:
    result = []
    visual_assets = visual_assets or {}
    display_content = display_content or {}
    attachment_indexes = {
        element_id: index for index, element_id in enumerate(visual_assets, start=1)
    }
    for hit in hits:
        payload = {
            "element_id": str(hit.element.id),
            "chunk_id": str(hit.element.id),
            "document_id": str(hit.element.document_id),
            "document_name": hit.element.document_name,
            "heading": hit.element.heading,
            "content": hit.element.content,
            "page_number": hit.element.page_number,
            "score": round(hit.score, 6),
            "source": hit.element.metadata.get("source", ""),
            "element_type": hit.element.element_type,
            "visual_extraction": hit.element.metadata.get("visual_extraction"),
        }
        asset = visual_assets.get(hit.element.id)
        if asset is not None:
            payload["visual_asset"] = {
                "mime_type": asset.mime_type,
                "page_number": asset.page_number,
                "sha256": asset.sha256,
                "bbox": asset.bbox,
                "attachment_index": attachment_indexes[hit.element.id],
            }
            if hit.element.id in display_content:
                payload["visual_asset"]["content"] = display_content[hit.element.id]
        result.append(payload)
    return result


def build_generation_prompt(
    question: str,
    hits: list[SearchHit],
    visual_assets: dict[UUID, VisualEvidenceAsset] | None = None,
) -> str:
    evidence = json.dumps(_evidence_payload(hits, visual_assets), ensure_ascii=False)
    return (
        "次の質問へ、取得根拠だけを使って回答してください。自由文の最終回答や分類は返さず、"
        "answer-output-v1のJSONだけを返してください。すべてのclaimにelement_idを引用してください。\n"
        "画像が添付される場合、visual_asset.attachment_indexが添付順（1始まり）です。\n"
        f"質問: {question}\n取得根拠: {evidence}"
    )


def build_classification_prompt(
    question: str, hits: list[SearchHit], answer_data: dict
) -> str:
    return build_classification_prompt_v1_from_payload(
        question, _evidence_payload(hits), answer_data
    )


def _classification_payload(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    return json.dumps(
        {
            "question": question,
            "retrieved_evidence": evidence,
            "generated_answer": answer_data,
        },
        ensure_ascii=False,
    )


def build_classification_prompt_v1_from_payload(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    payload = _classification_payload(question, evidence, answer_data)
    return (
        "classification-output-v1に従い、ラベルではなく5つの判定要因をJSONで返してください。"
        "corpus全体に答えが存在するかは判定しないでください。\n"
        f"判定対象: {payload}"
    )


def load_schema(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON Schemaのtop-levelがobjectではありません: {path}")
    return data


def _claim_log_rows(display: DisplayAnswer) -> list[dict]:
    return [
        {
            "claim_id": claim.claim_id,
            "ordinal": claim.ordinal,
            "text": claim.text,
            "evidence_element_ids": list(claim.evidence_element_ids),
        }
        for claim in display.visible_claims
    ]


def _classification_answer_payload(answer, raw_data: dict) -> dict:
    if raw_data.get("schema_version") != "2.0":
        return raw_data
    return {
        "schema_version": "2.0",
        "claims": [
            {
                "claim_id": claim.claim_id,
                "ordinal": claim.ordinal,
                "text": claim.text,
                "evidence_element_ids": [
                    str(value) for value in claim.evidence_element_ids
                ],
                "evidence_kind": claim.evidence_kind,
            }
            for claim in answer.claims
        ],
        "missing_conditions": [
            {
                "type": condition.condition_type,
                "description": condition.description,
                "evidence_element_ids": [
                    str(value) for value in condition.evidence_element_ids
                ],
            }
            for condition in answer.missing_conditions
        ],
        "date_calculations": raw_data["date_calculations"],
    }


def answer_question(
    question: str,
    *,
    embed_query: Callable[[str], list[float]],
    vector_index: VectorIndex,
    generator: StructuredLLMProvider,
    classifier: StructuredLLMProvider,
    event_logger: QueryEventLogger,
    answer_schema: dict,
    classification_schema: dict,
    top_k: int = 5,
    visual_asset_loader: Callable[[list[UUID]], list[VisualEvidenceAsset]]
    | None = None,
    asset_reader: AssetReader | None = None,
    max_visual_assets: int = 3,
    version_resolver: StructuredLLMProvider | None = None,
    version_resolution_schema: dict | None = None,
    version_resolution_confidence_threshold: float = (
        VERSION_RESOLUTION_CONFIDENCE_THRESHOLD
    ),
    generation_prompt_builder: Callable[
        [str, list[SearchHit], dict[UUID, VisualEvidenceAsset] | None], str
    ] = build_generation_prompt,
    generation_prompt_version: str = GENERATION_PROMPT_VERSION,
) -> dict:
    if max_visual_assets < 0:
        raise ValueError("max_visual_assetsは0以上である必要があります")
    if (version_resolver is None) != (version_resolution_schema is None):
        raise ValueError("version resolverとschemaは両方指定する必要があります")
    if not 0 <= version_resolution_confidence_threshold <= 1:
        raise ValueError("version resolver confidence閾値は0から1で指定してください")
    request_id = event_logger.start_request(question)
    hits = vector_index.search(embed_query(question), limit=top_k)
    event_logger.record_retrieval(request_id, hits)

    generation_result = None
    visual_assets: dict[UUID, VisualEvidenceAsset] = {}
    visual_content: dict[UUID, bytes] = {}
    classification_result = None
    classification = None
    version_resolution_metadata = {
        "status": "NOT_CONFIGURED" if version_resolver is None else "NOT_REQUIRED",
        "applied": False,
        "fallback_used": False,
        "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    try:
        if visual_asset_loader is not None:
            loaded_assets = visual_asset_loader([hit.element.id for hit in hits])
            loaded_by_id = {asset.element_id: asset for asset in loaded_assets}
            visual_assets = {
                hit.element.id: loaded_by_id[hit.element.id]
                for hit in hits
                if hit.element.id in loaded_by_id
            }
            visual_assets = dict(list(visual_assets.items())[:max_visual_assets])
        prompt = generation_prompt_builder(question, hits, visual_assets)
        if visual_assets:
            if not hasattr(generator, "generate_structured_with_media"):
                raise TypeError("図表根拠にはmultimodal対応generatorが必要です")
            reader = asset_reader or LocalAssetReader()
            visual_content = {
                element_id: reader.read(asset)
                for element_id, asset in visual_assets.items()
            }
            media = [
                (visual_content[element_id], asset.mime_type)
                for element_id, asset in visual_assets.items()
            ]
            generation_result = generator.generate_structured_with_media(
                prompt, answer_schema, media=media
            )
        else:
            generation_result = generator.generate_structured(prompt, answer_schema)
        answer_data = generation_result.data
        answer = apply_date_calculations(parse_answer_output(answer_data))
        validate_answer_evidence(answer, {hit.element.id for hit in hits})
    except Exception as exc:
        event_logger.record_generation_attempt(
            request_id,
            provider=generator.provider_name,
            model=generator.model,
            prompt_version=generation_prompt_version,
            response_data=generation_result.data if generation_result else None,
            input_tokens=generation_result.input_tokens if generation_result else 0,
            output_tokens=generation_result.output_tokens if generation_result else 0,
            status="GENERATION_FAILED",
            error_summary=str(exc)[:1000],
        )
        raise
    event_logger.record_generation_attempt(
        request_id,
        provider=generation_result.provider,
        model=generation_result.model,
        prompt_version=generation_prompt_version,
        response_data=answer_data,
        input_tokens=generation_result.input_tokens,
        output_tokens=generation_result.output_tokens,
        status="SUCCESS",
        error_summary=None,
    )

    classification_status = "SUCCESS"
    semantic_fallback_used = False
    semantic_error = None
    try:
        classification_result = classifier.generate_structured(
            build_classification_prompt(
                question, hits, _classification_answer_payload(answer, answer_data)
            ),
            classification_schema,
        )
        classification_data = classification_result.data
        classification = parse_classification_output(classification_data)
        if classification.factors.version_conflict and version_resolver is not None:
            resolver_result = None
            resolver_factors = {"baseline_version_conflict": True, "applied": False}
            resolver_status = "RESOLUTION_FAILED"
            resolver_fallback = True
            resolver_error = None
            try:
                resolver_result = version_resolver.generate_structured(
                    build_version_resolution_prompt(
                        question, _evidence_payload(hits), answer_data
                    ),
                    version_resolution_schema,
                )
                resolution = parse_version_resolution(resolver_result.data)
                retrieved_ids = {hit.element.id for hit in hits}
                if not set(resolution.evidence_element_ids) <= retrieved_ids:
                    raise ValueError("resolverが取得外の根拠IDを返しました")
                resolver_factors.update(
                    {
                        "resolved_version_conflict": resolution.version_conflict,
                        "resolution_basis": resolution.resolution_basis,
                        "evidence_element_ids": [
                            str(item) for item in resolution.evidence_element_ids
                        ],
                    }
                )
                if resolution.confidence < version_resolution_confidence_threshold:
                    resolver_status = "LOW_CONFIDENCE_FALLBACK"
                else:
                    candidate = replace(
                        classification,
                        factors=replace(
                            classification.factors,
                            version_conflict=resolution.version_conflict,
                        ),
                    )
                    try:
                        render_display_answer(answer, candidate)
                    except ValueError as exc:
                        resolver_status = "DISPLAY_CONTRACT_FALLBACK"
                        resolver_error = str(exc)
                    else:
                        classification = candidate
                        resolver_status = "SUCCESS"
                        resolver_fallback = False
                        resolver_factors["applied"] = True
                version_resolution_metadata = {
                    **resolver_result.metadata(),
                    "status": resolver_status,
                    "applied": resolver_factors["applied"],
                    "fallback_used": resolver_fallback,
                    "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
                    "version_conflict": resolution.version_conflict,
                    "resolution_basis": resolution.resolution_basis,
                    "evidence_element_ids": resolver_factors["evidence_element_ids"],
                    "confidence": resolution.confidence,
                }
            except Exception as exc:
                resolver_error = str(exc)
                version_resolution_metadata = {
                    "provider": (
                        resolver_result.provider
                        if resolver_result
                        else version_resolver.provider_name
                    ),
                    "model": (
                        resolver_result.model
                        if resolver_result
                        else version_resolver.model
                    ),
                    "status": "RESOLUTION_FAILED",
                    "applied": False,
                    "fallback_used": True,
                    "prompt_version": VERSION_RESOLUTION_PROMPT_VERSION,
                    "input_tokens": resolver_result.input_tokens
                    if resolver_result
                    else 0,
                    "output_tokens": (
                        resolver_result.output_tokens if resolver_result else 0
                    ),
                    "error_summary": str(exc)[:1000],
                }
            event_logger.record_classification_attempt(
                request_id,
                provider=version_resolution_metadata["provider"],
                model=version_resolution_metadata["model"],
                prompt_version=VERSION_RESOLUTION_PROMPT_VERSION,
                factors=resolver_factors,
                derived_label=None,
                confidence=version_resolution_metadata.get("confidence"),
                status=resolver_status,
                fallback_used=resolver_fallback,
                error_summary=resolver_error[:1000] if resolver_error else None,
            )
        try:
            display = render_display_answer(answer, classification)
        except DisplayContractError as exc:
            display = render_pipeline_inconsistency(answer, classification, exc)
            classification_status = display.status
            semantic_fallback_used = True
            semantic_error = str(exc)
    except Exception as exc:
        event_logger.record_classification_attempt(
            request_id,
            provider=(
                classification_result.provider
                if classification_result
                else classifier.provider_name
            ),
            model=classification_result.model
            if classification_result
            else classifier.model,
            prompt_version=CLASSIFICATION_PROMPT_VERSION,
            factors=asdict(classification.factors) if classification else None,
            derived_label=(
                derive_label(classification.factors) if classification else None
            ),
            confidence=classification.confidence if classification else None,
            status="CLASSIFICATION_FAILED",
            fallback_used=False,
            error_summary=str(exc)[:1000],
        )
        raise
    event_logger.record_classification_attempt(
        request_id,
        provider=classification_result.provider,
        model=classification_result.model,
        prompt_version=CLASSIFICATION_PROMPT_VERSION,
        factors=asdict(classification.factors),
        derived_label=derive_label(classification.factors),
        confidence=classification.confidence,
        status=classification_status,
        fallback_used=(
            version_resolution_metadata["fallback_used"] or semantic_fallback_used
        ),
        error_summary=semantic_error,
    )
    event_logger.record_answer_result(
        request_id,
        label=display.label,
        display_text=display.text,
        claims=_claim_log_rows(display),
        status=display.status,
    )
    return {
        "request_id": str(request_id),
        "question": question,
        "answer": display.text,
        "answer_label": display.label,
        "answer_status": display.status,
        "degraded": display.status != "SUCCESS",
        "invariant_code": display.invariant_code,
        "claims": _claim_log_rows(display),
        "references": _evidence_payload(
            hits, visual_assets, display_content=visual_content
        ),
        "generation": generation_result.metadata(),
        "visual_evidence_count": len(visual_assets),
        "classification": classification_result.metadata(),
        "classification_decision_version": (
            VERSION_RESOLUTION_DECISION_VERSION
            if version_resolver is not None
            else CLASSIFICATION_DECISION_VERSION
        ),
        "version_resolution": version_resolution_metadata,
    }
