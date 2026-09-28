import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.manage_rag_v2 import (
    CLOUD_SMOKE_QUESTION,
    bootstrap_cloud,
    extract_visual,
    ingest_reviewed_visual_fixtures,
    ingest_visual,
)
from src.visual_extractor import VisualExtractionCandidate


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
            "scripts.manage_rag_v2.ingest_reviewed_visual_fixtures",
            return_value={"reviewed_visual_fixtures": 6},
        ) as ingest_visuals,
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
    ingest_visuals.assert_called_once_with()
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
        patch("scripts.manage_rag_v2.ingest_reviewed_visual_fixtures"),
        patch(
            "scripts.manage_rag_v2.reconcile",
            return_value={"consistent": False},
        ),
        patch("scripts.manage_rag_v2.generate_qdrant_answer") as generate,
    ):
        with pytest.raises(RuntimeError, match="indexが一致しません"):
            bootstrap_cloud()

    generate.assert_not_called()


def test_ingest_reviewed_visual_fixtures_publishes_six_runtime_renders() -> None:
    rendered = type("Rendered", (), {"sha256": "runtime-render-sha"})()
    with (
        patch("scripts.manage_rag_v2.PostgresDocumentRepository") as repository,
        patch("scripts.manage_rag_v2.QdrantVectorIndex") as vector_index,
        patch("scripts.manage_rag_v2.get_asset_store") as asset_store,
        patch("scripts.manage_rag_v2.get_embeddings") as embeddings,
        patch("scripts.manage_rag_v2.render_pdf_page", return_value=rendered) as render,
        patch("scripts.manage_rag_v2.ingest_visual_pdf") as ingest_runtime,
    ):
        result = ingest_reviewed_visual_fixtures()

    assert result == {"reviewed_visual_fixtures": 6}
    assert render.call_count == 6
    assert ingest_runtime.call_count == 6
    document_keys = {
        call.kwargs["document_key"] for call in ingest_runtime.call_args_list
    }
    assert document_keys == {
        "visual-demo-flowchart_dev_001",
        "visual-demo-flowchart_dev_002",
        "visual-demo-timeline_dev_001",
        "visual-demo-table_dev_001",
        "visual-demo-form_dev_001",
        "visual-demo-table_dev_002",
    }
    for call in ingest_runtime.call_args_list:
        assert call.kwargs["reviewed"] is True
        assert call.kwargs["extraction"]["source_image_sha256"] == "runtime-render-sha"
        assert call.kwargs["repository"] is repository.return_value
        assert call.kwargs["vector_index"] is vector_index.return_value
        assert call.kwargs["asset_store"] is asset_store.return_value
        assert call.kwargs["embeddings"] is embeddings.return_value


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
        patch("scripts.manage_rag_v2.get_asset_store") as asset_store,
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


def test_extract_visual_writes_review_candidate_without_ingesting(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "candidate.json"
    candidate = VisualExtractionCandidate(
        raw_data={"schema_version": "1.0", "kind": "flowchart"},
        data={"schema_version": "1.0", "kind": "flowchart"},
        provider="fake",
        model="visual-test",
        prompt_version="visual-extraction-v1",
        input_tokens=120,
        output_tokens=80,
        request_id="request-1",
        validation_errors=("edge bboxが不正です",),
        normalized_bbox_count=3,
        normalized_structure_count=1,
    )
    rendered = object()
    with (
        patch("scripts.manage_rag_v2.render_pdf_page", return_value=rendered),
        patch("scripts.manage_rag_v2.GeminiProvider") as provider,
        patch(
            "scripts.manage_rag_v2.extract_visual_candidate",
            return_value=candidate,
        ) as extract_candidate,
    ):
        result = extract_visual(
            pdf_path=tmp_path / "source.pdf",
            page_number=2,
            kind_hint="flowchart",
            output_path=output_path,
        )

    assert json.loads(output_path.read_text(encoding="utf-8")) == candidate.data
    assert result["review_status"] == "REVIEW_REQUIRED"
    assert result["input_tokens"] == 120
    assert result["validation_errors"] == ["edge bboxが不正です"]
    assert result["normalized_bbox_count"] == 3
    assert result["normalized_structure_count"] == 1
    extract_candidate.assert_called_once_with(
        page=rendered,
        kind_hint="flowchart",
        provider=provider.return_value,
    )


def test_extract_visual_does_not_overwrite_review_candidate(tmp_path: Path) -> None:
    output_path = tmp_path / "candidate.json"
    output_path.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="上書きしません"):
        extract_visual(
            pdf_path=tmp_path / "source.pdf",
            page_number=1,
            kind_hint="flowchart",
            output_path=output_path,
        )

    assert output_path.read_text(encoding="utf-8") == "preserve"
