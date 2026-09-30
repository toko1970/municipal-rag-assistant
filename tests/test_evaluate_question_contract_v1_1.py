import json
from pathlib import Path

from eval.evaluate_question_contract_v1_1 import score_contract, validate_dataset


DATASET = Path("eval/question_contract_v1_mechanism_cases.json")


def test_v11_reuses_same_fixed_gate_dataset() -> None:
    cases = validate_dataset(json.loads(DATASET.read_text(encoding="utf-8")))

    assert len(cases) == 18


def test_v11_score_uses_response_shape_request_and_scope_quotes() -> None:
    case = {
        "expected_facets": [
            {"answer_type": "amount", "requirement_patterns": ["A日", "額"]},
            {"answer_type": "amount", "requirement_patterns": ["B日", "額"]},
        ],
        "required_input_patterns": ["他条件.*満た"],
    }
    response = {
        "requested_facets": [
            {
                "request_quote": "各日の支給額は？",
                "response_shape": "amount",
                "scope_quotes": ["A日"],
            },
            {
                "request_quote": "各日の支給額は？",
                "response_shape": "amount",
                "scope_quotes": ["B日"],
            },
        ],
        "input_facts": [{"source_quote": "他条件は満たす"}],
    }

    assert score_contract(case, response)["contract_ok"] is True


def test_v11_score_rejects_reframed_yes_no_as_explanation() -> None:
    case = {
        "expected_facets": [
            {"answer_type": "eligibility", "requirement_patterns": ["補填", "でき"]}
        ],
        "required_input_patterns": [],
    }
    response = {
        "requested_facets": [
            {
                "request_quote": "補填できますか",
                "response_shape": "explanation",
                "scope_quotes": [],
            }
        ],
        "input_facts": [],
    }

    assert score_contract(case, response)["contract_ok"] is False


def test_v11_semantic_review_covers_every_completed_case() -> None:
    result_dir = Path("eval/results/question_contract_v1_1_gate_b1_v1")
    records = [
        json.loads(line)
        for line in (result_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    review = json.loads(
        (result_dir / "semantic_review.json").read_text(encoding="utf-8")
    )

    assert {row["case_id"] for row in records} == {
        row["case_id"] for row in review["cases"]
    }
    assert review["semantic_contract_ok"] == 15
    assert review["semantic_contract_failed"] == 3
    assert review["automated_false_negative_count"] == 7
