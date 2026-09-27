from unittest.mock import patch

import src.rag_chain as rag_chain
from src.feedback import save_feedback


def test_qdrant_backend_routes_default_app_request() -> None:
    expected = {"request_id": "test", "answer": "回答"}
    with (
        patch.object(rag_chain, "RAG_BACKEND", "qdrant"),
        patch("src.rag_v2.generate_qdrant_answer", return_value=expected) as generate,
    ):
        result = rag_chain.generate_answer("質問")

    assert result == expected
    generate.assert_called_once_with("質問")


def test_injected_evaluation_path_stays_on_legacy_flow() -> None:
    class Provider:
        def generate(self, _prompt):
            return type(
                "Result",
                (),
                {
                    "text": "回答",
                    "metadata": lambda self: {"model": "fake"},
                },
            )()

    with patch.object(rag_chain, "RAG_BACKEND", "qdrant"):
        result = rag_chain.generate_answer(
            "質問",
            retrieve_fn=lambda _question: [],
            record_log=False,
            llm_provider=Provider(),
        )

    assert result["answer"] == "回答"


def test_request_id_feedback_is_saved_to_postgres_adapter() -> None:
    with patch(
        "src.persistence.repositories.PostgresEventLogger.record_feedback"
    ) as record:
        save_feedback(
            {"request_id": "00000000-0000-0000-0000-000000000001"},
            "採用した",
            "確認済み",
        )

    request_id, value, comment = record.call_args.args
    assert str(request_id) == "00000000-0000-0000-0000-000000000001"
    assert (value, comment) == ("採用した", "確認済み")
