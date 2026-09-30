import json
from pathlib import Path

import pytest

from eval.build_question_contract_v1_mechanism_cases import build
from eval.evaluate_question_contract_v1 import score_contract, validate_dataset


DATASET = Path("eval/question_contract_v1_mechanism_cases.json")


def test_question_contract_mechanism_fixture_is_reproducible() -> None:
    assert json.loads(DATASET.read_text(encoding="utf-8")) == build()


def test_question_contract_mechanism_fixture_has_fixed_slices() -> None:
    cases = validate_dataset(json.loads(DATASET.read_text(encoding="utf-8")))

    assert len(cases) == 18
    assert sum(case["slice"] == "over_abstention" for case in cases) == 9
    assert sum(case["slice"] == "dangerous_assertion" for case in cases) == 3
    assert sum(case["slice"] == "control" for case in cases) == 6


def test_score_contract_checks_facets_and_required_question_facts() -> None:
    case = {
        "expected_facets": [
            {"answer_type": "amount", "requirement_patterns": ["補助", "額"]},
            {
                "answer_type": "date",
                "requirement_patterns": ["提出|申請", "期限"],
            },
        ],
        "required_input_patterns": ["2027年10月10日", "8000"],
    }
    response = {
        "requested_facets": [
            {"answer_type": "date", "requirement": "申請期限"},
            {"answer_type": "amount", "requirement": "補助額"},
        ],
        "input_facts": [
            {"text": "2027年10月10日に受験"},
            {"text": "受験料8000円"},
        ],
    }

    assert score_contract(case, response)["contract_ok"] is True

    response["requested_facets"].pop()
    score = score_contract(case, response)
    assert score["facet_count_ok"] is False
    assert score["contract_ok"] is False


def test_validate_dataset_rejects_case_count_change() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    dataset["cases"].pop()

    with pytest.raises(ValueError, match="18件"):
        validate_dataset(dataset)
