from pathlib import Path

import pytest

from eval.evaluate_gemini_classifier_benchmark import run


def test_run_rejects_call_limit_before_constructing_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="logical external call上限は36"):
        run(
            dataset_path=Path("eval/classifier_model_benchmark_v1.json"),
            output_path=tmp_path / "result.json",
            max_logical_external_calls=35,
            max_cost_usd=0.05,
        )


def test_run_rejects_insufficient_cost_cap_before_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cost上限"):
        run(
            dataset_path=Path("eval/classifier_model_benchmark_v1.json"),
            output_path=tmp_path / "result.json",
            max_logical_external_calls=36,
            max_cost_usd=0.046,
        )
