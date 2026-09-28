from copy import deepcopy
import hashlib
from pathlib import Path

import fitz
import pytest

from eval.run_visual_holdout_predictions import (
    MAX_LOGICAL_EXTERNAL_CALLS,
    build_execution_plan,
    load_frozen_candidate,
    verify_document_inputs,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_plan_uses_public_frozen_artifacts_only() -> None:
    manifest, config = load_frozen_candidate()

    plan = build_execution_plan(manifest, config)

    assert plan["document_count"] == 6
    assert plan["scenario_count"] == 20
    assert plan["logical_external_call_limit"] == MAX_LOGICAL_EXTERNAL_CALLS
    assert plan["gold_available_to_runner"] is False
    assert plan["retry_count"] == 0


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
