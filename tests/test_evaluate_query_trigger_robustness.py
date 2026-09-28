import json

from config import BASE_DIR
from eval.evaluate_query_trigger_robustness import evaluate


def test_frozen_robustness_set_has_balanced_families_and_stable_ids() -> None:
    payload = json.loads(
        (BASE_DIR / "eval/query_trigger_robustness_cases.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["frozen_before_candidate_change"] is True
    assert payload["sealed_holdout"] is False
    assert len(payload["cases"]) == 40
    assert len({case["id"] for case in payload["cases"]}) == 40
    assert {case["expected_decomposition"] for case in payload["cases"]} <= {
        "none",
        "move_commute_stop",
        "birth_start_deadline",
    }


def test_evaluator_reports_a_deliberate_label_mismatch() -> None:
    payload = json.loads(
        (BASE_DIR / "eval/query_trigger_robustness_cases.json").read_text(
            encoding="utf-8"
        )
    )

    payload["cases"] = [dict(payload["cases"][0])]
    payload["cases"][0]["expected_decomposition"] = "none"
    records, summary = evaluate(payload)

    assert len(records) == 1
    assert summary["external_api_calls"] == 0
    assert summary["sealed_holdout_accessed"] is False
    assert summary["decomposition"]["false_positive"] == 1
    assert summary["failed_case_ids"] == ["G01"]
