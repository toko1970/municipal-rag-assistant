"""Validated PDF and visual-element ingestion for the first visual RAG slice."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import fitz
from config import BASE_DIR, EMBEDDING_MODEL_NAME
from src.asset_store import AssetStore, StoredAsset
from src.contracts import IndexableElement
from src.embedding_representation import contextual_heading_document_text
from src.ingestion import stable_uuid
from src.visual_validation import validate_gold


VISUAL_SCHEMA_PATH = BASE_DIR / "design/schemas/visual-extraction-v1.schema.json"
VISUAL_EMBEDDING_PROFILE_KEY = (
    f"gemini:{EMBEDDING_MODEL_NAME}:visual-description-v1"
)


class ReviewRequiredError(RuntimeError):
    pass


class VisualDocumentRepository(Protocol):
    def upsert_visual_element(
        self,
        *,
        source_path: str,
        document_name: str,
        element: IndexableElement,
        asset: StoredAsset,
        bbox: dict[str, float],
    ) -> IndexableElement: ...

    def mark_index_status(self, element_ids: list[UUID], status: str) -> None: ...

    def upsert_embedding_profile(
        self,
        profile_key: str,
        provider: str,
        model: str,
        dimensions: int,
        configuration: dict,
    ) -> UUID: ...


class VisualVectorIndex(Protocol):
    def ensure_collection(self, vector_size: int) -> None: ...

    def upsert(
        self,
        elements: list[IndexableElement],
        vectors: list[list[float]],
        embedding_profile: str,
    ) -> None: ...


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    png: bytes
    sha256: str
    width: int
    height: int


def render_pdf_page(pdf_path: Path, page_number: int, dpi: int = 150) -> RenderedPage:
    if page_number < 1:
        raise ValueError("page_numberは1以上である必要があります")
    with fitz.open(pdf_path) as document:
        if page_number > document.page_count:
            raise ValueError("page_numberがPDFのpage数を超えています")
        page = document[page_number - 1]
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        png = pixmap.tobytes("png")
    return RenderedPage(
        page_number=page_number,
        png=png,
        sha256=hashlib.sha256(png).hexdigest(),
        width=pixmap.width,
        height=pixmap.height,
    )


def load_visual_schema(path: Path = VISUAL_SCHEMA_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_visual_extraction(
    extraction: dict[str, Any], *, source_image_sha256: str
) -> None:
    schema = load_visual_schema()
    validate_gold(extraction, schema)
    if extraction["source_image_sha256"] != source_image_sha256:
        raise ValueError("抽出候補とpage imageのSHA-256が一致しません")


def visual_search_text(extraction: dict[str, Any]) -> str:
    kind = extraction["kind"]
    lines = [
        f"図表名: {extraction['title']}",
        f"種類: {kind}",
        f"ページ: {extraction['page']}",
    ]
    data = extraction["data"]
    if kind == "flowchart":
        nodes = {node["id"]: node for node in data["nodes"]}
        lines.append(
            "ノード: "
            + " / ".join(
                f"{node['id']}={node['text']}({node['node_type']})"
                for node in data["nodes"]
            )
        )
        lines.append(
            "経路: "
            + " / ".join(
                f"{nodes[edge['from']]['text']} -> {nodes[edge['to']]['text']}"
                + (f" [{edge['condition']}]" if edge["condition"] else "")
                for edge in data["edges"]
            )
        )
    elif kind == "timeline":
        lines.append(
            "時系列: "
            + " / ".join(
                f"{event['date_or_offset']}: {event['action']}"
                for event in data["events"]
            )
        )
    elif kind == "table":
        lines.append(
            "セル: "
            + " / ".join(
                f"行{cell['row'] + 1}列{cell['column'] + 1}: {cell['text']}"
                for cell in data["cells"]
            )
        )
    elif kind == "form":
        lines.append(
            "項目: "
            + " / ".join(
                f"{field['label']}: {field['example_value'] or '記入例なし'}"
                for field in data["fields"]
            )
        )
    return "\n".join(lines)


def build_visual_element(
    *, pdf_path: Path, document_key: str, document_name: str, extraction: dict[str, Any]
) -> IndexableElement:
    content_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    document_id = stable_uuid(f"document:{document_key}")
    version_id = stable_uuid(f"version:{document_id}:{content_hash}")
    element_id = stable_uuid(
        f"visual-element:{version_id}:{extraction['page']}:{extraction['kind']}:{extraction['title']}"
    )
    return IndexableElement(
        id=element_id,
        document_id=document_id,
        version_id=version_id,
        document_name=document_name,
        heading=extraction["title"],
        content=visual_search_text(extraction),
        element_type=extraction["kind"],
        page_number=extraction["page"],
        metadata={
            "document_key": document_key,
            "content_hash": content_hash,
            "visual_extraction": extraction,
            "review_status": "READY",
        },
    )


def ingest_visual_pdf(
    *,
    pdf_path: Path,
    document_key: str,
    document_name: str,
    extraction: dict[str, Any],
    reviewed: bool,
    repository: VisualDocumentRepository,
    vector_index: VisualVectorIndex,
    asset_store: AssetStore,
    embeddings: Any,
) -> dict[str, Any]:
    page = render_pdf_page(pdf_path, extraction["page"])
    validate_visual_extraction(extraction, source_image_sha256=page.sha256)
    if extraction["confidence"]["review_required"] and not reviewed:
        raise ReviewRequiredError("図表はreview完了まで検索対象へ登録できません")
    element = build_visual_element(
        pdf_path=pdf_path,
        document_key=document_key,
        document_name=document_name,
        extraction=extraction,
    )
    asset = asset_store.put_page_image(
        document_key=document_key,
        page_number=page.page_number,
        content=page.png,
    )
    repository.upsert_visual_element(
        source_path=str(pdf_path),
        document_name=document_name,
        element=element,
        asset=asset,
        bbox=extraction["bbox"],
    )
    try:
        vector = embeddings.embed_documents(
            [contextual_heading_document_text(element)],
            task_type="RETRIEVAL_DOCUMENT",
        )[0]
        repository.upsert_embedding_profile(
            profile_key=VISUAL_EMBEDDING_PROFILE_KEY,
            provider="gemini",
            model=EMBEDDING_MODEL_NAME,
            dimensions=len(vector),
            configuration={
                "task_type": "RETRIEVAL_DOCUMENT",
                "document_representation": "visual-description-v1",
            },
        )
        vector_index.ensure_collection(len(vector))
        vector_index.upsert([element], [vector], VISUAL_EMBEDDING_PROFILE_KEY)
    except Exception:
        repository.mark_index_status([element.id], "INDEX_FAILED")
        raise
    repository.mark_index_status([element.id], "INDEXED")
    return {
        "document_key": document_key,
        "element_id": str(element.id),
        "asset_key": asset.key,
        "page": page.page_number,
        "kind": extraction["kind"],
        "review_status": "READY",
        "index_status": "INDEXED",
    }
