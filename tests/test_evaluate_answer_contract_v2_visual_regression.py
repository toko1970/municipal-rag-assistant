from pathlib import Path

from eval.evaluate_answer_contract_v2_visual_regression import _manifest


def test_manifest_fixes_bounded_v2_conditions() -> None:
    manifest = _manifest(
        dataset_path=Path("eval/visual_fixtures/development_evaluation_set.json"),
        fixture_manifest_path=Path(
            "eval/visual_fixtures/manifests/development_manifest.json"
        ),
        max_cost_usd=0.06,
        max_logical_external_calls=121,
    )

    assert manifest["scenario_count"] == 30
    assert manifest["retry_count"] == 0
    assert manifest["sealed_holdout_accessed"] is False
    assert manifest["answer_schema"].endswith("answer-output-v2.schema.json")
