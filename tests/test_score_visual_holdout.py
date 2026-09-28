from eval.score_visual_holdout import score_scenarios


def test_blocked_predictions_are_not_reported_as_classification_accuracy() -> None:
    predictions = [
        {
            "scenario_id": "VH001",
            "status": "BLOCKED_BY_EXTRACTION_ERROR",
            "predicted_label": None,
        },
        {
            "scenario_id": "VH002",
            "status": "BLOCKED_BY_EXTRACTION_ERROR",
            "predicted_label": None,
        },
    ]
    gold = [
        {"scenario_id": "VH001", "expected_classification": "grounded"},
        {
            "scenario_id": "VH002",
            "expected_classification": "insufficient_documents",
        },
    ]

    result = score_scenarios(predictions, gold)

    assert result["blocked_by_extraction_error_count"] == 2
    assert result["classification_evaluated_count"] == 0
    assert result["classification_accuracy"] is None
    assert result["end_to_end_success_rate"] == 0.0
