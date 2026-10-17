import pytest

from src.question_contract_v1_1 import QuestionContractV11Error, parse


QUESTION = "A日に1時間、B日に2時間実施した。他条件は満たす。各日の支給額は？"


def _data() -> dict:
    return {
        "schema_version": "1.1-candidate",
        "status": "SUCCESS",
        "requested_facets": [
            {
                "facet_id": "facet-1",
                "request_quote": "各日の支給額は？",
                "response_shape": "amount",
                "scope_quotes": ["A日"],
            },
            {
                "facet_id": "facet-2",
                "request_quote": "各日の支給額は？",
                "response_shape": "amount",
                "scope_quotes": ["B日"],
            },
        ],
        "input_facts": [
            {
                "fact_id": "fact-1",
                "source_quote": "他条件は満たす",
                "fact_type": "condition",
                "applies_to_facet_ids": ["facet-1", "facet-2"],
            }
        ],
        "error_code": None,
    }


def test_parses_source_grounded_multi_target_contract() -> None:
    contract = parse(_data(), question=QUESTION)

    assert len(contract.facets) == 2
    assert contract.facets[0].scope_quotes == ("A日",)
    assert contract.input_facts[0].source_quote == "他条件は満たす"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("request_quote", "各日について支給額を教えて", "REQUEST_QUOTE_NOT_IN_QUESTION"),
        ("scope_quotes", ["C日"], "SCOPE_QUOTE_NOT_IN_QUESTION"),
    ],
)
def test_rejects_facet_text_not_copied_from_question(
    field: str, value: object, code: str
) -> None:
    data = _data()
    data["requested_facets"][0][field] = value

    with pytest.raises(QuestionContractV11Error) as exc_info:
        parse(data, question=QUESTION)

    assert exc_info.value.code == code


def test_rejects_invented_or_paraphrased_input_fact() -> None:
    data = _data()
    data["input_facts"][0]["source_quote"] = "必要条件はすべて充足済み"

    with pytest.raises(QuestionContractV11Error) as exc_info:
        parse(data, question=QUESTION)

    assert exc_info.value.code == "FACT_QUOTE_NOT_IN_QUESTION"


def test_rejects_overlapping_semantic_answer_types() -> None:
    data = _data()
    data["requested_facets"][0]["response_shape"] = "eligibility"

    with pytest.raises(QuestionContractV11Error) as exc_info:
        parse(data, question=QUESTION)

    assert exc_info.value.code == "SCHEMA_INVALID"


def test_rejects_duplicate_facet_for_same_request_and_scope() -> None:
    data = _data()
    data["requested_facets"][1]["scope_quotes"] = ["A日"]

    with pytest.raises(QuestionContractV11Error) as exc_info:
        parse(data, question=QUESTION)

    assert exc_info.value.code == "DUPLICATE_FACET"
