import pytest

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


@pytest.mark.parametrize("day", ["2028年2月29日", "2028-02-29", "2028/2/29"])
@pytest.mark.parametrize("wording", ["提出期限はいつですか？", "締切を教えて", "締め切りは？"])
def test_deadline_wording_and_date_formats_select_same_route(day, wording):
    assert should_use_deadline_calculation(f"{day}に住所変更しました。{wording}")


@pytest.mark.parametrize("question", [
    "住所変更日は2028年2月29日です。提出期限日はいつですか？",
    "2028年3月20日の講座で2時間教えます。休務時間と申込期限を教えてください。",
    "2028年2月29日に受験し8000円を払いました。補助額と提出期限を教えてください。",
])
def test_named_event_and_combined_requests_select_deadline_route(question):
    assert should_use_deadline_calculation(question)


@pytest.mark.parametrize("question", [
    "2027年2月29日に申請しました。提出期限はいつですか？",
    "2028-02-30に申請しました。提出期限日はいつですか？",
    "2028/13/01に申請しました。いつまでに出せますか？",
    "2028年2月29日に申請しました。提出期限は何日以内ですか？",
    "2028年2月29日に申請しました。何日後が期限ですか？",
    "2028年2月29日付の通知で、提出期限を教えてください。",
    "2028年2月29日に申請しました。休日の場合の締切はいつですか？",
    "2028年2月29日に申請しました。祝日を除いた締切はいつですか？",
    "2028年2月29日に申請しました。期限は3月5日で合っていますか？",
])
def test_invalid_dates_and_non_calendar_requests_do_not_select_route(question):
    assert not should_use_deadline_calculation(question)
