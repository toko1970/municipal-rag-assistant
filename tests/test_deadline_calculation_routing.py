from src.temporal_evidence import (
    build_deadline_calculation_prompt,
    should_use_deadline_calculation,
)
from src.query_service import build_deadline_classification_prompt


def test_routes_only_concrete_calendar_deadline_questions() -> None:
    assert should_use_deadline_calculation(
        "2027年10月10日に受験しました。提出期限は何日までですか？"
    )
    assert should_use_deadline_calculation(
        "2027/10/10に受験しました。具体的な日付を教えてください。"
    )
    assert not should_use_deadline_calculation("提出期限は何日以内ですか？")
    assert not should_use_deadline_calculation("2027年10月10日の支給額はいくらですか？")


def test_deadline_prompt_keeps_string_missing_conditions() -> None:
    prompt = build_deadline_calculation_prompt(
        "2027年10月10日の期限は？", [], None
    )

    assert "answer-output-v1.1" in prompt
    assert "missing_conditionsへ文字列" in prompt
    assert "date_calculations" in prompt


def test_deadline_classifier_trusts_verified_application_claim() -> None:
    prompt = build_deadline_classification_prompt(
        "2027年10月10日の期限は？", [], {"date_calculations": []}
    )

    assert "具体日claimは検証済み" in prompt
    assert "requires_case_facts=trueにしない" in prompt
