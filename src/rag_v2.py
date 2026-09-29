"""Composition root for the PostgreSQL and Qdrant text RAG."""

from __future__ import annotations

from config import (
    BASE_DIR,
    CLASSIFIER_MODEL_NAME,
    LLM_MODEL_NAME,
    TOP_K,
)
from src.asset_backend import get_asset_reader
from src.embeddings import get_embeddings
from src.llm_provider import GeminiProvider
from src.persistence.database import get_session_factory
from src.persistence.repositories import PostgresDocumentRepository, PostgresEventLogger
from src.qdrant_index import QdrantVectorIndex
from src.query_decomposition import DecomposedVectorIndex
from src.query_service import (
    CLASSIFICATION_PROMPT_V2_VERSION,
    answer_question,
    build_classification_prompt_v2,
    load_schema,
)
from src.temporal_evidence import (
    ANSWER_CONTRACT_V2_PROMPT_VERSION,
    build_answer_contract_v2_prompt,
)


ANSWER_SCHEMA_PATH = BASE_DIR / "design/schemas/answer-output-v2.schema.json"
CLASSIFICATION_SCHEMA_PATH = (
    BASE_DIR / "design/schemas/classification-output-v1.schema.json"
)
VERSION_RESOLUTION_SCHEMA_PATH = (
    BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
)


def generate_qdrant_answer(question: str) -> dict:
    embeddings = get_embeddings()
    session_factory = get_session_factory()
    repository = PostgresDocumentRepository(session_factory)
    vector_index = DecomposedVectorIndex(
        question=question,
        base_index=QdrantVectorIndex(),
        embed_query=embeddings.embed_query,
    )
    return answer_question(
        question,
        embed_query=embeddings.embed_query,
        vector_index=vector_index,
        generator=GeminiProvider(LLM_MODEL_NAME),
        classifier=GeminiProvider(CLASSIFIER_MODEL_NAME),
        event_logger=PostgresEventLogger(session_factory),
        answer_schema=load_schema(ANSWER_SCHEMA_PATH),
        classification_schema=load_schema(CLASSIFICATION_SCHEMA_PATH),
        version_resolver=GeminiProvider(CLASSIFIER_MODEL_NAME),
        version_resolution_schema=load_schema(VERSION_RESOLUTION_SCHEMA_PATH),
        top_k=TOP_K,
        generation_prompt_builder=build_answer_contract_v2_prompt,
        generation_prompt_version=ANSWER_CONTRACT_V2_PROMPT_VERSION,
        classification_prompt_builder=build_classification_prompt_v2,
        classification_prompt_version=CLASSIFICATION_PROMPT_V2_VERSION,
        visual_asset_loader=repository.get_visual_assets,
        asset_reader=get_asset_reader(),
    )
