from eval.analyze_retrieved_regression import analyze


def test_analysis_counts_candidate_regression_as_production_success() -> None:
    text = {
        "Q001": {
            "expected_label": "根拠十分",
            "predicted_label": "根拠十分",
            "classification_ok": True,
            "classification_factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
                "version_conflict": False,
                "requires_case_facts": False,
                "requires_policy_judgment": False,
            },
            "error": None,
        }
    }
    visual = {
        "VD001": {
            "expected_classification": "needs_judgment",
            "predicted_label": "文書不足",
            "classification_ok": False,
            "classification_factors": {
                "retrieval_sufficient": False,
                "answer_fully_supported": True,
                "version_conflict": False,
                "requires_case_facts": False,
                "requires_policy_judgment": True,
            },
            "required_fixture_retrieved": True,
            "error": None,
        }
    }
    top_k = {
        "records": [
            {
                "question_id": "Q001",
                "retrieval_applicable": True,
                "metrics": {"8": {"evidence_hit": True}},
            }
        ]
    }
    review = {
        "reviewed_text_questions": 1,
        "reviewed_visual_questions": 1,
        "text_failures": {},
        "visual_failures": {"classification_failure": ["VD001"]},
    }

    result = analyze(text, visual, top_k, review)

    assert result["summary"]["combined"] == {
        "classification_failure": 1,
        "success": 1,
    }
    assert result["summary"]["production_decision_v1_combined"] == {"success": 2}
    assert result["summary"]["decision_regressions"] == ["VD001"]
