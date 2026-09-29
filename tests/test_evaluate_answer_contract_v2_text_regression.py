from eval.evaluate_answer_contract_v2_text_regression import _classification_ok, _summary


def test_classification_requires_a_completed_result() -> None:
    row = {"expected_answer_type": "根拠十分"}

    assert not _classification_ok(row, None)
    assert _classification_ok(row, {"answer_label": "根拠十分"})


def test_summary_keeps_semantic_fallback_out_of_success() -> None:
    records = [
        {
            "error": None,
            "retrieval_applicable": True,
            "retrieval_ok": True,
            "classification_ok": True,
            "answer_status": "SUCCESS",
            "logical_external_calls": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_usd": 0.001,
        },
        {
            "error": None,
            "retrieval_applicable": True,
            "retrieval_ok": True,
            "classification_ok": True,
            "answer_status": "PIPELINE_INCONSISTENCY",
            "logical_external_calls": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_usd": 0.001,
        },
    ]

    summary = _summary(records, stop_reason="COMPLETED", max_cost_usd=0.14)

    assert summary["classification_correct"] == 2
    assert summary["semantic_success"] == 1
    assert summary["logical_external_calls"] == 4
