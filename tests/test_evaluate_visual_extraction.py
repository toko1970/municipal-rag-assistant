import copy
import json
from pathlib import Path

from eval.evaluate_visual_extraction import evaluate_visual_extraction


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "design/schemas/visual-extraction-v1.schema.json").read_text()
)
GOLD = json.loads(
    (ROOT / "eval/visual_fixtures/gold/flowchart_dev_001.json").read_text()
)


def test_identical_visual_extraction_passes_all_gates() -> None:
    metrics = evaluate_visual_extraction(copy.deepcopy(GOLD), GOLD, SCHEMA)

    assert metrics.gold_elements == 12
    assert metrics.matched_elements == 12
    assert metrics.element_recall == 1.0
    assert metrics.important_values_exact is True
    assert metrics.mean_bbox_iou == 1.0
    assert metrics.gate_passed is True


def test_incorrect_important_value_fails_exact_value_and_recall_gates() -> None:
    candidate = copy.deepcopy(GOLD)
    candidate["data"]["nodes"][-1]["text"] = "処理終了"

    metrics = evaluate_visual_extraction(candidate, GOLD, SCHEMA)

    assert metrics.matched_elements == 10
    assert metrics.element_recall == 10 / 12
    assert metrics.important_values_exact is False
    assert metrics.gate_passed is False


def test_equivalent_japanese_wave_dash_is_not_counted_as_content_error() -> None:
    candidate = copy.deepcopy(GOLD)
    candidate["data"]["edges"][2]["condition"] = "あ～り"
    gold = copy.deepcopy(candidate)
    gold["data"]["edges"][2]["condition"] = "あ〜り"

    metrics = evaluate_visual_extraction(candidate, gold, SCHEMA)

    assert metrics.important_values_exact is True
    assert metrics.element_recall == 1.0
