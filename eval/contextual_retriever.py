"""親見出しを埋め込み対象へ加える検索方式の評価用実装。"""

from functools import lru_cache
import hashlib
import shutil

from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import BASE_DIR, EMBEDDING_MODEL_NAME, TOP_K
from src.chunking import split_documents
from src.document_loader import load_markdown_documents
from src.embeddings import get_embeddings


CONTEXTUAL_DB_DIR = BASE_DIR / ".eval_cache" / "contextual_chroma_db"
CONTEXTUAL_COLLECTION_NAME = "municipality_rag_docs_contextual"
FINGERPRINT_FILE = CONTEXTUAL_DB_DIR / ".fingerprint"
HEADING_KEYS = ("見出し1", "見出し2", "見出し3")


def heading_path(metadata: dict) -> str:
    """チャンクが属する見出し階層を一行にまとめる。"""
    return " > ".join(
        str(metadata[key]) for key in HEADING_KEYS if metadata.get(key)
    )


def contextualize_chunks(chunks: list[Document]) -> list[Document]:
    """本文の前に親を含む見出し階層を加え、検索用チャンクを作る。"""
    contextualized = []
    for chunk in chunks:
        path = heading_path(chunk.metadata)
        prefix = f"見出し階層: {path}\n\n" if path else ""
        contextualized.append(
            Document(
                page_content=f"{prefix}{chunk.page_content}",
                metadata={**chunk.metadata, "contextual_heading": path},
            )
        )
    return contextualized


def chunks_fingerprint(chunks: list[Document]) -> str:
    """文書やEmbeddingモデルが変わった場合に評価用DBを作り直す。"""
    digest = hashlib.sha256()
    digest.update(EMBEDDING_MODEL_NAME.encode("utf-8"))
    for chunk in chunks:
        digest.update(chunk.page_content.encode("utf-8"))
        for key in ("document_id", "source", *HEADING_KEYS):
            digest.update(str(chunk.metadata.get(key, "")).encode("utf-8"))
    return digest.hexdigest()


def _cache_is_current(fingerprint: str) -> bool:
    return (
        (CONTEXTUAL_DB_DIR / "chroma.sqlite3").exists()
        and FINGERPRINT_FILE.exists()
        and FINGERPRINT_FILE.read_text(encoding="utf-8").strip() == fingerprint
    )


@lru_cache(maxsize=1)
def get_contextual_vector_store() -> Chroma:
    """評価用DBを、文書内容が同じ間は再利用する。"""
    chunks = contextualize_chunks(split_documents(load_markdown_documents()))
    fingerprint = chunks_fingerprint(chunks)
    embeddings = get_embeddings()

    if _cache_is_current(fingerprint):
        return Chroma(
            collection_name=CONTEXTUAL_COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(CONTEXTUAL_DB_DIR),
        )

    if CONTEXTUAL_DB_DIR.exists():
        shutil.rmtree(CONTEXTUAL_DB_DIR)
    CONTEXTUAL_DB_DIR.mkdir(parents=True, exist_ok=True)
    store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=CONTEXTUAL_COLLECTION_NAME,
        persist_directory=str(CONTEXTUAL_DB_DIR),
    )
    FINGERPRINT_FILE.write_text(fingerprint, encoding="utf-8")
    return store


def retrieve_documents_with_score(query: str, top_k: int = TOP_K):
    """親見出しの文脈を含めた評価用DBから検索する。"""
    return get_contextual_vector_store().similarity_search_with_score(
        query=query,
        k=top_k,
    )
