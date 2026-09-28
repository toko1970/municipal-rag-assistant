from copy import deepcopy
import hashlib
import json
from pathlib import Path

import fitz
import pytest

from eval.run_visual_holdout_predictions import (
    MAX_LOGICAL_EXTERNAL_CALLS,
    build_execution_plan,
    build_success_bundle,
    freeze_failed_predictions,
    load_frozen_candidate,
    verify_document_inputs,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_success_bundle_explicitly_records_that_gold_was_not_accessed() -> None:
    bundle = build_success_bundle(
        run_manifest={"run_id": "successful-run"},
        extraction_records=[{"document_id": "vh_doc_test"}],
        predictions=[{"scenario_id": "VH001"}],
        input_tokens=100,
        output_tokens=20,
    )

    assert bundle["summary"]["sealed_gold_accessed"] is False


def test_plan_uses_public_frozen_artifacts_only() -> None:
    manifest, config = load_frozen_candidate()

    plan = build_execution_plan(manifest, config)

    assert plan["document_count"] == 6
    assert plan["scenario_count"] == 20
    assert plan["logical_external_call_limit"] == MAX_LOGICAL_EXTERNAL_CALLS
    assert plan["gold_available_to_runner"] is False
    assert plan["retry_count"] == 0


def test_plan_derives_limits_from_manifest_size() -> None:
    manifest = {
        "holdout_id": "visual-sealed-holdout-v2",
        "candidate": {"git_commit": "a" * 40, "config_manifest_sha256": "b" * 64},
        "documents": [{"document_id": f"doc-{index}"} for index in range(4)],
        "questions": {"count": 10},
    }
    config = {"execution_policy": {"retry_count": 0}}

    plan = build_execution_plan(manifest, config)

    assert plan["logical_external_call_limit"] == 35
    assert plan["minimum_reserved_cost_usd"] == pytest.approx(0.14)


def test_document_verification_does_not_require_a_gold_directory(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "vh_doc_test.pdf"
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(pdf_path)
    content = pdf_path.read_bytes()
    manifest = {
        "documents": [
            {
                "document_id": "vh_doc_test",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ]
    }

    verified = verify_document_inputs(manifest, tmp_path)

    assert verified == [(manifest["documents"][0], pdf_path)]


def test_plan_refuses_a_non_frozen_runtime_setting(monkeypatch) -> None:
    import eval.run_visual_holdout_predictions as runner

    manifest, config = load_frozen_candidate()
    changed = deepcopy(config)
    changed["pipeline"]["retrieval"]["top_k"] = 999
    original_load = runner.load_json

    def fake_load(path: Path):
        if path.name == "candidate_config.json":
            return changed
        return original_load(path)

    monkeypatch.setattr(runner, "load_json", fake_load)

    with pytest.raises(ValueError, match="top_k"):
        runner.load_frozen_candidate()


def test_freeze_failure_records_twenty_blocked_outcomes(
    tmp_path: Path, monkeypatch
) -> None:
    import eval.run_visual_holdout_predictions as runner

    output_dir = tmp_path / "failed-run"
    extraction_dir = output_dir / "extraction"
    extraction_dir.mkdir(parents=True)
    (output_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "failed-run",
                "sealed_gold_accessed": False,
            }
        )
    )
    invalid = {
        "schema_version": "1.0",
        "kind": "flowchart",
        "title": "invalid",
        "page": 1,
        "source_image_sha256": "0" * 64,
        "bbox": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9},
        "data": {"type": "flowchart", "nodes": [], "edges": []},
        "confidence": {"source": "test", "value": 0.1, "review_required": True},
    }
    for suffix in ("raw", "normalized"):
        (extraction_dir / f"vh_doc_a7.{suffix}.json").write_text(json.dumps(invalid))
    manifest, config = load_frozen_candidate()
    monkeypatch.setattr(runner, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        runner,
        "questions_path",
        lambda _manifest: REPOSITORY_ROOT / "eval/visual_holdout/questions.json",
    )
    monkeypatch.setattr(
        runner, "load_frozen_candidate", lambda _manifest_path: (manifest, config)
    )

    bundle, bundle_hash = freeze_failed_predictions(output_dir)

    assert len(bundle["predictions"]) == 20
    assert bundle["summary"]["question_attempt_count"] == 0
    assert bundle["summary"]["failed_document_id"] == "vh_doc_a7"
    assert len(bundle_hash) == 64
    assert (output_dir / "predictions.json").is_file()
