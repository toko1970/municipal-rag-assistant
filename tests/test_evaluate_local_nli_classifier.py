from eval.evaluate_local_nli_classifier import binary_metrics, summarize


def test_binary_metrics_counts_each_error_type() -> None:
    result = binary_metrics([True, True, False, False], [True, False, True, False])

    assert result["true_positive"] == 1
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1
    assert result["f1"] == 0.5


def test_summary_derives_label_and_flags_unsafe_grounded_error() -> None:
    factors = {
        "retrieval_sufficient": False,
        "answer_fully_supported": False,
        "requires_case_facts": False,
        "requires_policy_judgment": False,
        "version_conflict": False,
    }
    case = {
        "case_id": "C01",
        "modality": "text",
        "expected_factors": factors,
        "expected_label": "文書不足",
    }
    predicted = {
        "retrieval_sufficient": True,
        "answer_fully_supported": True,
        "requires_case_facts": False,
        "requires_policy_judgment": False,
        "version_conflict": False,
    }
    records = [
        {"case_id": "C01", "factor": factor, "predicted": value}
        for factor, value in predicted.items()
    ]

    result = summarize([case], records)

    assert result["case_results"][0]["predicted_label"] == "根拠十分"
    assert result["critical_error_count"] == 1
