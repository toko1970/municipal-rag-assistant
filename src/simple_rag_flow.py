"""One-call text-answer flow for the approved evaluation candidate."""

from __future__ import annotations

from uuid import UUID

from langchain_core.documents import Document

from config import LLM_MODEL_NAME, TOP_K
from src.asset_store import LocalAssetReader, VisualEvidenceAsset
from src.asset_backend import get_asset_reader
from src.embeddings import get_embeddings
from src.llm_provider import GeminiProvider
from src.query_decomposition import DecomposedVectorIndex
from src.qdrant_index import QdrantVectorIndex
from src.rag_chain import build_context, build_prompt
from src.freeform_prompt_candidate import (
    GENERATOR_MAX_OUTPUT_TOKENS as CANDIDATE_MAX_OUTPUT_TOKENS,
    GENERATOR_MODEL as CANDIDATE_GENERATOR_MODEL,
    PROMPT_CONFIG_SHA256 as CANDIDATE_PROMPT_CONFIG_SHA256,
    build_prompt as build_candidate_prompt,
)


CANDIDATE_PROMPT_VERSION = f"freeform-candidate:{CANDIDATE_PROMPT_CONFIG_SHA256}"


def _freeform_label(answer: str) -> str | None:
    labels = ("根拠十分", "判断要", "文書不足")
    for line in answer.splitlines():
        value = line.strip().removeprefix("回答分類:").strip().strip("（）() ")
        if value in labels:
            return value
    return None


def _as_documents(hits):
    return [
        (
            Document(
                page_content=hit.element.content,
                metadata={
                    "document_id": str(hit.element.metadata.get("document_key") or hit.element.document_id),
                    "document_name": hit.element.document_name,
                    "見出し2": hit.element.heading,
                    "chunk_id": hit.element.metadata.get("ordinal", hit.rank),
                    "source": hit.element.metadata.get("source_path", ""),
                    "element_id": str(hit.element.id),
                },
            ),
            hit.score,
        )
        for hit in hits
    ]


def generate_simple_qdrant_answer(
    question: str,
    *,
    embed_query=None,
    vector_index=None,
    generator=None,
    visual_asset_loader=None,
    asset_reader=None,
    max_visual_assets: int = 3,
    record_log: bool = True,
    prompt_variant: str = "baseline",
    retrieved_hits=None,
    event_logger=None,
) -> dict:
    """Use production retrieval followed by the legacy one-call text prompt."""
    request_id = event_logger.start_request(question) if record_log and event_logger else None
    if retrieved_hits is None:
        embeddings = get_embeddings() if embed_query is None else None
        embed_query = embed_query or embeddings.embed_query
        base_index = vector_index or QdrantVectorIndex()
        index = DecomposedVectorIndex(
            question=question,
            base_index=base_index,
            embed_query=embed_query,
        )
        hits = index.search(embed_query(question), TOP_K)
    else:
        hits = list(retrieved_hits)
    if request_id is not None:
        event_logger.record_retrieval(request_id, hits)
    documents = _as_documents(hits)
    context = build_context(documents)
    if prompt_variant not in {
        "baseline",
        "autoresearch_candidate",
    }:
        raise ValueError(f"未対応のprompt_variantです: {prompt_variant}")
    if prompt_variant == "autoresearch_candidate":
        prompt = build_candidate_prompt(question, context)
    else:
        prompt = build_prompt(question, context)
    if generator is None:
        if prompt_variant == "autoresearch_candidate":
            generator = GeminiProvider(
                CANDIDATE_GENERATOR_MODEL,
                temperature=0,
                max_output_tokens=CANDIDATE_MAX_OUTPUT_TOKENS,
            )
        else:
            generator = GeminiProvider(LLM_MODEL_NAME, max_output_tokens=1024)
    if visual_asset_loader is None and record_log and event_logger is None:
        from src.persistence.database import get_session_factory
        from src.persistence.repositories import PostgresDocumentRepository

        repository = PostgresDocumentRepository(get_session_factory())
        visual_asset_loader = repository.get_visual_assets
        asset_reader = asset_reader or get_asset_reader()
    if max_visual_assets < 0:
        raise ValueError("max_visual_assetsは0以上である必要があります")
    visual_assets: dict[UUID, VisualEvidenceAsset] = {}
    visual_content: dict[UUID, bytes] = {}
    if visual_asset_loader is not None:
        loaded = visual_asset_loader([hit.element.id for hit in hits])
        by_id = {asset.element_id: asset for asset in loaded}
        visual_assets = {
            hit.element.id: by_id[hit.element.id]
            for hit in hits
            if hit.element.id in by_id
        }
        visual_assets = dict(list(visual_assets.items())[:max_visual_assets])
    try:
        if visual_assets:
            reader = asset_reader or LocalAssetReader()
            for element_id, asset in visual_assets.items():
                visual_content[element_id] = reader.read(asset)
            media = [
                (visual_content[element_id], asset.mime_type)
                for element_id, asset in visual_assets.items()
            ]
            if not hasattr(generator, "generate_with_media"):
                raise TypeError("図表根拠にはmultimodal対応generatorが必要です")
            response = generator.generate_with_media(prompt, media=media)
        else:
            response = generator.generate(prompt)
    except Exception as error:
        if request_id is not None:
            event_logger.record_generation_attempt(
                request_id,
                provider=getattr(generator, "provider_name", "gemini"),
                model=getattr(generator, "model", CANDIDATE_GENERATOR_MODEL),
                prompt_version=(CANDIDATE_PROMPT_VERSION if prompt_variant == "autoresearch_candidate" else f"simple-rag:{prompt_variant}"),
                response_data=None,
                input_tokens=0,
                output_tokens=0,
                status="FAILED",
                error_summary=type(error).__name__,
            )
            event_logger.record_answer_result(
                request_id,
                label=None,
                display_text="回答の生成中にエラーが発生しました。時間を置いて再実行してください。",
                claims=[],
                status="GENERATION_FAILED",
            )
        raise
    metadata = response.metadata()
    answer_text = response.text
    answer_label = _freeform_label(answer_text)
    result = {
        "question": question,
        "answer": answer_text,
        "answer_label": answer_label,
        "answer_status": "SUCCESS",
        "degraded": False,
        "retrieved_documents": hits,
        "references": [],
        "generation": metadata,
        "prompt_variant": prompt_variant,
    }
    if request_id is not None:
        event_logger.record_generation_attempt(
            request_id,
            provider=metadata.get("provider", "gemini"),
            model=metadata.get("model", getattr(generator, "model", CANDIDATE_GENERATOR_MODEL)),
            prompt_version=(CANDIDATE_PROMPT_VERSION if prompt_variant == "autoresearch_candidate" else f"simple-rag:{prompt_variant}"),
            response_data=None,
            input_tokens=int(metadata.get("input_tokens", 0)),
            output_tokens=int(metadata.get("output_tokens", 0)),
            status="SUCCESS",
        )
        result["request_id"] = str(request_id)
        event_logger.record_answer_result(
            request_id,
            label=answer_label,
            display_text=answer_text,
            claims=[],
            status="SUCCESS",
        )

    references = [
        {
            "document_id": document.metadata["document_id"],
            "document_name": document.metadata["document_name"],
            "heading": document.metadata["見出し2"],
            "chunk_id": document.metadata["chunk_id"],
            "score": round(score, 4),
            "source": document.metadata["source"],
        }
        for (document, score) in documents
    ]
    for reference, (document, _score) in zip(references, documents, strict=True):
        element_id = document.metadata.get("element_id")
        asset = visual_assets.get(UUID(str(element_id))) if element_id else None
        if asset is not None:
            reference["visual_asset"] = {
                "content": visual_content[UUID(str(element_id))],
                "mime_type": asset.mime_type,
                "page_number": asset.page_number,
            }
    result["references"] = references
    if request_id is None and record_log:
        from src.logger import save_rag_log

        save_rag_log(result)
    return result
