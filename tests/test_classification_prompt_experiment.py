from pathlib import Path

from eval.analyze_classification_decision_rule import analyze
from eval.compare_classification_prompts import (
    _load_json,
    build_classification_prompt_v2_from_payload,
    build_classification_prompt_v3_from_payload,
    summarize,
    validate_cases,
)
from src.query_service import build_classification_prompt_v1_from_payload


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPOSITORY_ROOT / "eval/classification_prompt_development_cases.json"
DATASET_V2 = REPOSITORY_ROOT / "eval/classification_prompt_development_cases_v2.json"


def test_development_cases_have_fixed_balanced_counts() -> None:
    dataset = _load_json(DATASET)

    cases = validate_cases(dataset)

    assert len(cases) == 12
    assert dataset["modality_counts"] == {"text": 6, "visual": 6}
    assert dataset["expected_counts"] == {
        "根拠十分": 6,
        "判断要": 4,
        "文書不足": 2,
    }


def test_candidate_prompt_defines_a_concrete_missing_fact_boundary() -> None:
    prompt = build_classification_prompt_v2_from_payload(
        "質問", [{"content": "根拠"}], {"missing_conditions": []}
    )
    baseline = build_classification_prompt_v1_from_payload(
        "質問", [{"content": "根拠"}], {"missing_conditions": []}
    )

    assert "一般的な『個別事情の確認』を推測" in prompt
    assert "以上・以下・未満・超" in prompt
    assert "一般的な『個別事情の確認』を推測" not in baseline


def test_example_prompt_and_adversarial_cases_cover_both_directions() -> None:
    dataset = _load_json(DATASET_V2)
    cases = validate_cases(dataset)
    prompt = build_classification_prompt_v3_from_payload(
        "質問", [{"content": "根拠"}], {"missing_conditions": []}
    )

    assert len(cases) == 14
    assert "例A" in prompt and "例B" in prompt and "例C" in prompt
    assert {case["case_id"] for case in cases} >= {"CPD-T07", "CPD-V07"}


def test_summary_keeps_text_and_visual_results_separate() -> None:
    records = [
        {
            "prompt": prompt,
            "modality": modality,
            "correct": correct,
            "error": None,
        }
        for prompt, modality, correct in (
            ("baseline", "text", True),
            ("baseline", "visual", False),
            ("candidate", "text", True),
            ("candidate", "visual", True),
        )
    ]

    result = summarize(records, case_count=2)

    assert result["by_prompt"]["baseline"]["accuracy"] == 0.5
    assert result["by_prompt"]["candidate"]["accuracy"] == 1.0
    assert result["by_prompt"]["candidate"]["text_correct"] == 1
    assert result["by_prompt"]["candidate"]["visual_correct"] == 1


def test_decision_rule_turns_unsupported_case_flag_into_insufficient() -> None:
    dataset = {
        "cases": [
            {
                "case_id": "case-1",
                "generated_answer": {
                    "schema_version": "1.0",
                    "claims": [],
                    "missing_conditions": ["対象資料"],
                },
            }
        ]
    }
    response = {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "factors": {
            "retrieval_sufficient": False,
            "answer_fully_supported": False,
            "requires_case_facts": True,
            "requires_policy_judgment": False,
            "version_conflict": False,
        },
        "confidence": 1.0,
        "error_code": None,
    }
    bundle = {
        "records": [
            {
                "case_id": "case-1",
                "modality": "text",
                "prompt": "baseline",
                "expected_label": "文書不足",
                "predicted_label": "判断要",
                "correct": False,
                "error": None,
                "response": response,
            }
        ]
    }

    result = analyze(bundle, dataset)

    record = result["records"][0]
    assert record["effective_label"] == "文書不足"
    assert record["effective_correct"] is True
