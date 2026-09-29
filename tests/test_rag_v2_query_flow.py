from types import SimpleNamespace
from unittest.mock import patch

from src.query_decomposition import DecomposedVectorIndex
from src.query_service import (
    CLASSIFICATION_PROMPT_VERSION,
    DEADLINE_CLASSIFICATION_PROMPT_VERSION,
    build_classification_prompt,
    build_deadline_classification_prompt,
)
from src.rag_v2 import generate_qdrant_answer
from src.temporal_evidence import (
    DEADLINE_CALCULATION_PROMPT_VERSION,
    TEMPORAL_GENERATION_PROMPT_VERSION,
    build_deadline_calculation_prompt,
    build_temporal_generation_prompt,
)


def test_composition_root_connects_retrieval_and_temporal_candidates() -> None:
    def embed_query(_question: str) -> list[float]:
        return [1.0]

    embeddings = SimpleNamespace(embed_query=embed_query)
    base_index = object()
    repository = SimpleNamespace(get_visual_assets=lambda _ids: [])
    expected = {"answer": "ok"}

    with (
        patch("src.rag_v2.get_embeddings", return_value=embeddings),
        patch("src.rag_v2.get_session_factory", return_value=object()),
        patch("src.rag_v2.PostgresDocumentRepository", return_value=repository),
        patch("src.rag_v2.PostgresEventLogger", return_value=object()),
        patch("src.rag_v2.QdrantVectorIndex", return_value=base_index),
        patch("src.rag_v2.GeminiProvider", return_value=object()),
        patch("src.rag_v2.get_asset_reader", return_value=object()),
        patch("src.rag_v2.answer_question", return_value=expected) as answer,
    ):
        result = generate_qdrant_answer("質問")

    assert result == expected
    kwargs = answer.call_args.kwargs
    assert isinstance(kwargs["vector_index"], DecomposedVectorIndex)
    assert kwargs["vector_index"].question == "質問"
    assert kwargs["vector_index"].base_index is base_index
    assert kwargs["vector_index"].embed_query is embed_query
    assert kwargs["answer_schema"]["properties"]["schema_version"]["const"] == "1.0"
    assert kwargs["generation_prompt_builder"] is build_temporal_generation_prompt
    assert kwargs["generation_prompt_version"] == TEMPORAL_GENERATION_PROMPT_VERSION
    assert kwargs["classification_prompt_builder"] is build_classification_prompt
    assert kwargs["classification_prompt_version"] == CLASSIFICATION_PROMPT_VERSION


def test_composition_root_routes_concrete_deadline_to_v1_1() -> None:
    embeddings = SimpleNamespace(embed_query=lambda _question: [1.0])
    repository = SimpleNamespace(get_visual_assets=lambda _ids: [])

    with (
        patch("src.rag_v2.get_embeddings", return_value=embeddings),
        patch("src.rag_v2.get_session_factory", return_value=object()),
        patch("src.rag_v2.PostgresDocumentRepository", return_value=repository),
        patch("src.rag_v2.PostgresEventLogger", return_value=object()),
        patch("src.rag_v2.QdrantVectorIndex", return_value=object()),
        patch("src.rag_v2.GeminiProvider", return_value=object()),
        patch("src.rag_v2.get_asset_reader", return_value=object()),
        patch("src.rag_v2.answer_question", return_value={}) as answer,
    ):
        generate_qdrant_answer("2027年10月10日に受験しました。提出期限は何日までですか？")

    kwargs = answer.call_args.kwargs
    assert kwargs["answer_schema"]["properties"]["schema_version"]["const"] == "1.1"
    assert kwargs["generation_prompt_builder"] is build_deadline_calculation_prompt
    assert kwargs["generation_prompt_version"] == DEADLINE_CALCULATION_PROMPT_VERSION
    assert kwargs["classification_prompt_builder"] is build_deadline_classification_prompt
    assert (
        kwargs["classification_prompt_version"]
        == DEADLINE_CLASSIFICATION_PROMPT_VERSION
    )
