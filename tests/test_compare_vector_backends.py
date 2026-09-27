from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from pathlib import Path

from eval.compare_vector_backends import (
    evaluate_backend_pair,
    filter_questions,
    load_or_create_query_vectors,
)


def test_shared_embedding_is_called_once_per_question_for_two_backends() -> None:
    questions = [
        {
            "question_id": "Q1",
            "question": "質問1",
            "expected_document_ids": "DOC-001",
            "expected_answer_type": "根拠十分",
        },
        {
            "question_id": "Q2",
            "question": "質問2",
            "expected_document_ids": "DOC-002",
            "expected_answer_type": "根拠十分",
        },
    ]
    calls = []

    def embed(question):
        calls.append(question)
        return [float(len(calls))]

    def search(vector, _top_k):
        document_id = "DOC-001" if vector == [1.0] else "DOC-002"
        return [(SimpleNamespace(metadata={"document_id": document_id}), 0.9)]

    with redirect_stdout(StringIO()):
        chroma, qdrant, embedding_calls = evaluate_backend_pair(
            questions,
            embed_query=embed,
            chroma_search=search,
            qdrant_search=search,
        )

    assert calls == ["質問1", "質問2"]
    assert embedding_calls == 2
    assert [row["hit_at_1"] for row in chroma] == [1, 1]
    assert [row["hit_at_1"] for row in qdrant] == [1, 1]


def test_filters_one_expression_per_scenario() -> None:
    questions = [
        {"question": "標準", "variant_type": "formal"},
        {"question": "口語", "variant_type": "colloquial"},
    ]

    assert filter_questions(questions, "formal") == [questions[0]]


def test_batches_query_embeddings_and_reuses_validated_cache(tmp_path: Path) -> None:
    class Embeddings:
        def __init__(self):
            self.calls = []

        def embed_documents(self, texts, **kwargs):
            self.calls.append((texts, kwargs))
            return [[float(index)] for index, _ in enumerate(texts)]

    questions = [{"question": "質問1"}, {"question": "質問2"}]
    cache = tmp_path / "query-vectors.json"
    embeddings = Embeddings()

    vectors, requests, cache_hit = load_or_create_query_vectors(
        cache, questions, embeddings=embeddings
    )
    cached_vectors, cached_requests, cached_hit = load_or_create_query_vectors(
        cache, questions, embeddings=embeddings
    )

    assert vectors == {"質問1": [0.0], "質問2": [1.0]}
    assert cached_vectors == vectors
    assert requests == 1
    assert cached_requests == 0
    assert not cache_hit
    assert cached_hit
    assert embeddings.calls == [
        (
            ["質問1", "質問2"],
            {"batch_size": 100, "task_type": "RETRIEVAL_QUERY"},
        )
    ]
