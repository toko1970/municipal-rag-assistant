from eval.build_classifier_gold_correction import build


def test_gold_correction_recomputes_saved_regression_summary() -> None:
    result = build()

    assert result["evaluation_set_version"] == "1.2"
    assert result["model_or_prompt_changed"] is False
    assert result["summary"] == {
        "total": 130,
        "success": 117,
        "classification_correct": 121,
        "primary_causes": {
            "answer_generation_failure": 6,
            "classification_failure": 4,
            "retrieval_failure": 3,
            "success": 117,
        },
        "classification_mismatches": [
            "Q066",
            "Q126",
            "Q176",
            "Q196",
            "Q291",
            "Q386",
            "Q391",
            "VD004",
            "VD024",
        ],
        "primary_classification_failures": ["Q126", "Q176", "Q196", "VD024"],
    }
