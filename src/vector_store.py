import shutil

from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
    DOCS_DIR,
)

from src.embeddings import get_embeddings


def vector_store_exists() -> bool:
    """永続化済みのChroma DBが存在するか確認する。"""

    return (CHROMA_DB_DIR / "chroma.sqlite3").exists()


def create_vector_store(
    chunks: list[Document],
    reset_db: bool = True,
) -> Chroma:
    """
    Chromaを作成する。
    """

    if reset_db and CHROMA_DB_DIR.exists():
        shutil.rmtree(CHROMA_DB_DIR)

    embeddings = get_embeddings()

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=CHROMA_COLLECTION_NAME,
        persist_directory=str(CHROMA_DB_DIR),
    )

    return vector_store

def load_vector_store() -> Chroma:
    """
    保存済みChromaを読み込む。
    """

    embeddings = get_embeddings()

    vector_store = Chroma(
        collection_name=CHROMA_COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DB_DIR),
    )

    return vector_store


def load_or_create_vector_store() -> Chroma:
    """
    保存済みのChromaを読み込む。

    Streamlit Community Cloudなどの新規環境では、リポジトリ内の
    Markdown文書から初回アクセス時にベクトルDBを作成する。
    """

    if vector_store_exists():
        return load_vector_store()

    from src.chunking import split_documents
    from src.document_loader import load_markdown_documents

    documents = load_markdown_documents()
    if not documents:
        raise FileNotFoundError(
            f"検索対象のMarkdown文書が見つかりません: {DOCS_DIR}"
        )

    chunks = split_documents(documents)
    return create_vector_store(chunks, reset_db=True)
