"""Dependency-injected text RAG v2 query flow."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID

from src.answering import (
    DisplayAnswer,
    derive_label,
    parse_answer_output,
    parse_classification_output,
    render_display_answer,
    validate_answer_evidence,
)
from src.asset_store import AssetReader, LocalAssetReader, VisualEvidenceAsset
from src.contracts import SearchHit, VectorIndex
from src.llm_provider import StructuredLLMProvider, StructuredLLMResult


GENERATION_PROMPT_VERSION = "answer-claims-v1"
CLASSIFICATION_PROMPT_VERSION = "answer-classification-v1"


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
        element_id: index
        for index, element_id in enumerate(visual_assets, start=1)
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
    evidence = json.dumps(
        _evidence_payload(hits, visual_assets), ensure_ascii=False
    )
    return (
        "次の質問へ、取得根拠だけを使って回答してください。自由文の最終回答や分類は返さず、"
        "answer-output-v1のJSONだけを返してください。すべてのclaimにelement_idを引用してください。\n"
        "画像が添付される場合、visual_asset.attachment_indexが添付順（1始まり）です。\n"
        f"質問: {question}\n取得根拠: {evidence}"
    )


def build_classification_prompt(
    question: str, hits: list[SearchHit], answer_data: dict
) -> str:
    payload = json.dumps(
        {
            "question": question,
            "retrieved_evidence": _evidence_payload(hits),
            "generated_answer": answer_data,
        },
        ensure_ascii=False,
    )
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
    visual_asset_loader: Callable[[list[UUID]], list[VisualEvidenceAsset]] | None = None,
    asset_reader: AssetReader | None = None,
    max_visual_assets: int = 3,
) -> dict:
    if max_visual_assets < 0:
        raise ValueError("max_visual_assetsは0以上である必要があります")
    request_id = event_logger.start_request(question)
    hits = vector_index.search(embed_query(question), limit=top_k)
    event_logger.record_retrieval(request_id, hits)

    generation_result = None
    visual_assets: dict[UUID, VisualEvidenceAsset] = {}
    visual_content: dict[UUID, bytes] = {}
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
        prompt = build_generation_prompt(question, hits, visual_assets)
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
        answer = parse_answer_output(answer_data)
        validate_answer_evidence(answer, {hit.element.id for hit in hits})
    except Exception as exc:
        event_logger.record_generation_attempt(
            request_id,
            provider=generator.provider_name,
            model=generator.model,
            prompt_version=GENERATION_PROMPT_VERSION,
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
        prompt_version=GENERATION_PROMPT_VERSION,
        response_data=answer_data,
        input_tokens=generation_result.input_tokens,
        output_tokens=generation_result.output_tokens,
        status="SUCCESS",
        error_summary=None,
    )

    try:
        classification_result = classifier.generate_structured(
            build_classification_prompt(question, hits, answer_data),
            classification_schema,
        )
        classification_data = classification_result.data
        classification = parse_classification_output(classification_data)
        display = render_display_answer(answer, classification)
    except Exception as exc:
        event_logger.record_classification_attempt(
            request_id,
            provider=classifier.provider_name,
            model=classifier.model,
            prompt_version=CLASSIFICATION_PROMPT_VERSION,
            factors=None,
            derived_label=None,
            confidence=None,
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
        status="SUCCESS",
        fallback_used=False,
        error_summary=None,
    )
    event_logger.record_answer_result(
        request_id,
        label=display.label,
        display_text=display.text,
        claims=_claim_log_rows(display),
    )
    return {
        "request_id": str(request_id),
        "question": question,
        "answer": display.text,
        "answer_label": display.label,
        "claims": _claim_log_rows(display),
        "references": _evidence_payload(
            hits, visual_assets, display_content=visual_content
        ),
        "generation": generation_result.metadata(),
        "visual_evidence_count": len(visual_assets),
        "classification": classification_result.metadata(),
    }
