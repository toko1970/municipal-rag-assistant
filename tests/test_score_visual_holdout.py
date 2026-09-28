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


def test_completed_prediction_scores_each_stage_and_end_to_end() -> None:
    predictions = [
        {
            "scenario_id": "VH2-001",
            "predicted_label": "根拠十分",
            "retrieved_document_ids": ["vh2_doc_flow"],
            "answer": "申請後に所属長の承認へ進みます。",
        }
    ]
    gold = [
        {
            "scenario_id": "VH2-001",
            "expected_classification": "grounded",
            "required_document_ids": ["vh2_doc_flow"],
            "expected_answer_key_terms": ["所属長", "承認"],
        }
    ]

    result = score_scenarios(predictions, gold)

    assert result["classification_accuracy"] == 1.0
    assert result["required_document_retrieval_rate"] == 1.0
    assert result["answer_key_coverage_rate"] == 1.0
    assert result["end_to_end_success_rate"] == 1.0
