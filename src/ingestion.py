"""Deterministic Markdown ingestion shared by PostgreSQL and Qdrant."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from config import DOCS_DIR, EMBEDDING_MODEL_NAME
from src.chunking import split_documents
from src.contracts import IndexableElement
from src.document_loader import parse_markdown_with_metadata
from src.embeddings import get_embeddings
from src.persistence.repositories import PostgresDocumentRepository
from src.qdrant_index import QdrantVectorIndex


EMBEDDING_PROFILE_KEY = f"gemini:{EMBEDDING_MODEL_NAME}:document-v1"


def stable_uuid(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, value)


def build_markdown_elements(file_path: Path) -> list[IndexableElement]:
    metadata, body = parse_markdown_with_metadata(file_path)
    document_key = str(metadata.get("document_id") or file_path.name)
    document_name = str(metadata.get("document_name") or file_path.stem)
    content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    document_id = stable_uuid(f"document:{document_key}")
    version_id = stable_uuid(f"version:{document_id}:{content_hash}")

    from langchain_core.documents import Document

    chunks = split_documents(
        [Document(page_content=body, metadata={**metadata, "document_name": document_name})]
    )
    elements: list[IndexableElement] = []
    for ordinal, chunk in enumerate(chunks):
        element_id = stable_uuid(f"element:{version_id}:{ordinal}")
        element_metadata = {
            **chunk.metadata,
            "document_key": document_key,
            "content_hash": content_hash,
            "ordinal": ordinal,
        }
        elements.append(
            IndexableElement(
                id=element_id,
                document_id=document_id,
                version_id=version_id,
                document_name=document_name,
                heading=str(chunk.metadata.get("見出し2", "")),
                content=chunk.page_content,
                metadata=element_metadata,
            )
        )
    return elements


def ingest_markdown_documents(
    repository: PostgresDocumentRepository,
    vector_index: QdrantVectorIndex,
    docs_dir: Path = DOCS_DIR,
) -> dict[str, int]:
    embeddings = get_embeddings()
    document_count = 0
    element_count = 0
    for file_path in sorted(docs_dir.glob("*.md")):
        elements = build_markdown_elements(file_path)
        if not elements:
            continue
        repository.upsert_markdown_elements(
            source_path=str(file_path),
            document_name=elements[0].document_name,
            elements=elements,
        )
        try:
            vectors = embeddings.embed_documents([item.content for item in elements])
            repository.upsert_embedding_profile(
                profile_key=EMBEDDING_PROFILE_KEY,
                provider="gemini",
                model=EMBEDDING_MODEL_NAME,
                dimensions=len(vectors[0]),
                configuration={"task_type": "document-v1"},
            )
            vector_index.ensure_collection(len(vectors[0]))
            vector_index.upsert(elements, vectors, EMBEDDING_PROFILE_KEY)
        except Exception:
            repository.mark_index_status([item.id for item in elements], "INDEX_FAILED")
            raise
        repository.mark_index_status([item.id for item in elements], "INDEXED")
        document_count += 1
        element_count += len(elements)
    return {"documents": document_count, "elements": element_count}
