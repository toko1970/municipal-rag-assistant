from pathlib import Path
import shutil

from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
)

from src.embeddings import get_embeddings

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