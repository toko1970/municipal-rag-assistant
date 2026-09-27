from unittest.mock import patch

import pytest

from scripts.manage_rag_v2 import CLOUD_SMOKE_QUESTION, bootstrap_cloud


def test_bootstrap_cloud_runs_storage_setup_before_answer_smoke() -> None:
    answer = {
        "request_id": "00000000-0000-0000-0000-000000000001",
        "answer_label": "根拠十分",
        "references": [{"element_id": "one"}],
    }
    with (
        patch("scripts.manage_rag_v2.migrate") as migrate,
        patch(
            "scripts.manage_rag_v2.ingest",
            return_value={"documents": 5, "elements": 86},
        ) as ingest,
        patch(
            "scripts.manage_rag_v2.reconcile",
            return_value={
                "postgres_indexed_elements": 86,
                "qdrant_points": 86,
                "missing_in_qdrant": [],
                "unexpected_in_qdrant": [],
                "consistent": True,
            },
        ) as reconcile,
        patch(
            "scripts.manage_rag_v2.generate_qdrant_answer", return_value=answer
        ) as generate,
    ):
        result = bootstrap_cloud()

    migrate.assert_called_once_with()
    ingest.assert_called_once_with()
    reconcile.assert_called_once_with()
    generate.assert_called_once_with(CLOUD_SMOKE_QUESTION)
    assert result["migration"] == "head"
    assert result["smoke"] == {
        "question": CLOUD_SMOKE_QUESTION,
        "request_id": answer["request_id"],
        "answer_label": "根拠十分",
        "references": 1,
    }


def test_bootstrap_cloud_stops_before_smoke_when_indexes_differ() -> None:
    with (
        patch("scripts.manage_rag_v2.migrate"),
        patch("scripts.manage_rag_v2.ingest"),
        patch(
            "scripts.manage_rag_v2.reconcile",
            return_value={"consistent": False},
        ),
        patch("scripts.manage_rag_v2.generate_qdrant_answer") as generate,
    ):
        with pytest.raises(RuntimeError, match="indexが一致しません"):
            bootstrap_cloud()

    generate.assert_not_called()
