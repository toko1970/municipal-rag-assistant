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
    CLASSIFICATION_PROMPT_VERSION,
    DEADLINE_CLASSIFICATION_PROMPT_VERSION,
    answer_question,
    build_classification_prompt,
    build_deadline_classification_prompt,
    load_schema,
)
from src.temporal_evidence import (
    DEADLINE_CALCULATION_PROMPT_VERSION,
    TEMPORAL_GENERATION_PROMPT_VERSION,
    build_deadline_calculation_prompt,
    build_temporal_generation_prompt,
    should_use_deadline_calculation,
)


ANSWER_SCHEMA_V1_PATH = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
ANSWER_SCHEMA_V1_1_PATH = BASE_DIR / "design/schemas/answer-output-v1.1.schema.json"
CLASSIFICATION_SCHEMA_PATH = (
    BASE_DIR / "design/schemas/classification-output-v1.schema.json"
)
VERSION_RESOLUTION_SCHEMA_PATH = (
    BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
)


def generate_qdrant_answer(question: str) -> dict:
    deadline_mode = should_use_deadline_calculation(question)
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
        answer_schema=load_schema(
            ANSWER_SCHEMA_V1_1_PATH if deadline_mode else ANSWER_SCHEMA_V1_PATH
        ),
        classification_schema=load_schema(CLASSIFICATION_SCHEMA_PATH),
        version_resolver=GeminiProvider(CLASSIFIER_MODEL_NAME),
        version_resolution_schema=load_schema(VERSION_RESOLUTION_SCHEMA_PATH),
        top_k=TOP_K,
        generation_prompt_builder=(
            build_deadline_calculation_prompt
            if deadline_mode
            else build_temporal_generation_prompt
        ),
        generation_prompt_version=(
            DEADLINE_CALCULATION_PROMPT_VERSION
            if deadline_mode
            else TEMPORAL_GENERATION_PROMPT_VERSION
        ),
        classification_prompt_builder=(
            build_deadline_classification_prompt
            if deadline_mode
            else build_classification_prompt
        ),
        classification_prompt_version=(
            DEADLINE_CLASSIFICATION_PROMPT_VERSION
            if deadline_mode
            else CLASSIFICATION_PROMPT_VERSION
        ),
        visual_asset_loader=repository.get_visual_assets,
        asset_reader=get_asset_reader(),
    )
