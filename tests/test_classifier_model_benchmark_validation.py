from copy import deepcopy
import json
from pathlib import Path

import pytest

from eval.validate_classifier_model_benchmark import validate_benchmark


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval/classifier_model_benchmark_v1.json"
SCHEMA = ROOT / "design/schemas/classifier-model-benchmark-v1.schema.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_committed_benchmark_is_valid() -> None:
    validate_benchmark(load(DATASET), load(SCHEMA))


def test_rejects_label_that_disagrees_with_factor_gold() -> None:
    dataset = load(DATASET)
    dataset["cases"][0]["expected_label"] = "判断要"
    dataset["expected_counts"]["根拠十分"] -= 1
    dataset["expected_counts"]["判断要"] += 1

    with pytest.raises(ValueError, match="factorから導出したラベル"):
        validate_benchmark(dataset, load(SCHEMA))


def test_rejects_unapproved_case_in_approved_benchmark() -> None:
    dataset = deepcopy(load(DATASET))
    dataset["review_status"] = "approved"

    with pytest.raises(ValueError, match="未承認annotation"):
        validate_benchmark(dataset, load(SCHEMA))
