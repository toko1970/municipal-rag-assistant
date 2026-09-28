import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.manage_rag_v2 import (
    CLOUD_SMOKE_QUESTION,
    bootstrap_cloud,
    ingest_visual,
)


ROOT = Path(__file__).resolve().parents[1]


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


def test_ingest_visual_wires_reviewed_candidate_to_runtime_boundaries(
    tmp_path: Path,
) -> None:
    extraction_path = tmp_path / "candidate.json"
    extraction_path.write_text(json.dumps({"kind": "flowchart"}), encoding="utf-8")
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"pdf")
    expected = {"element_id": "visual-1", "index_status": "INDEXED"}

    with (
        patch("scripts.manage_rag_v2.PostgresDocumentRepository") as repository,
        patch("scripts.manage_rag_v2.QdrantVectorIndex") as vector_index,
        patch("scripts.manage_rag_v2.LocalAssetStore") as asset_store,
        patch("scripts.manage_rag_v2.get_embeddings") as embeddings,
        patch(
            "scripts.manage_rag_v2.ingest_visual_pdf", return_value=expected
        ) as ingest_runtime,
    ):
        result = ingest_visual(
            pdf_path=pdf_path,
            extraction_path=extraction_path,
            document_key="VIS-FLOW-001",
            document_name="通勤手当申請処理フロー",
            reviewed=True,
        )

    assert result == expected
    ingest_runtime.assert_called_once_with(
        pdf_path=pdf_path,
        document_key="VIS-FLOW-001",
        document_name="通勤手当申請処理フロー",
        extraction={"kind": "flowchart"},
        reviewed=True,
        repository=repository.return_value,
        vector_index=vector_index.return_value,
        asset_store=asset_store.return_value,
        embeddings=embeddings.return_value,
    )


def test_ingest_visual_rejects_unreviewed_candidate(tmp_path: Path) -> None:
    extraction_path = tmp_path / "candidate.json"
    extraction_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="--reviewed"):
        ingest_visual(
            pdf_path=tmp_path / "source.pdf",
            extraction_path=extraction_path,
            document_key="VIS-FLOW-001",
            document_name="通勤手当申請処理フロー",
            reviewed=False,
        )
