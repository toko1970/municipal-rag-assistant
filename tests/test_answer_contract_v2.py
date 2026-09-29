from datetime import date, time
from uuid import uuid4

import jsonschema

from config import BASE_DIR
from src.answering import parse_answer_output
from src.deadline_calculator import apply_date_calculations, calculate_deadline
from src.query_service import load_schema
from src.temporal_evidence import build_answer_contract_v2_prompt


def _v2_answer(
    evidence_id: str,
    *,
    anchor_date: str = "2027-10-10",
    offset_value: int = 20,
    counting_rule: str = "next_day_is_day_1",
    cutoff_time: str | None = "12:00:00",
) -> dict:
    return {
        "schema_version": "2.0",
        "claims": [
            {
                "claim_id": "claim-1",
                "ordinal": 1,
                "text": "提出期限は翌日を1日目とした20暦日目です。",
                "evidence_element_ids": [evidence_id],
                "evidence_kind": "text",
            }
        ],
        "missing_conditions": [],
        "date_calculations": [
            {
                "calculation_id": "date-1",
                "result_label": "提出期限",
                "anchor_date": anchor_date,
                "offset_value": offset_value,
                "offset_unit": "calendar_day",
                "counting_rule": counting_rule,
                "cutoff_time": cutoff_time,
                "evidence_element_ids": [evidence_id],
            }
        ],
    }


def test_v2_schema_and_parser_accept_typed_contract() -> None:
    evidence_id = str(uuid4())
    data = _v2_answer(evidence_id)
    schema = load_schema(BASE_DIR / "design/schemas/answer-output-v2.schema.json")

    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(data)
    parsed = parse_answer_output(data)

    assert parsed.date_calculations[0].anchor_date == date(2027, 10, 10)
    assert parsed.date_calculations[0].cutoff_time == time(12, 0)


def test_calendar_day_calculation_handles_month_end_and_noon() -> None:
    answer = parse_answer_output(_v2_answer(str(uuid4())))

    enriched = apply_date_calculations(answer)

    assert enriched.claims[-1].text == "提出期限は2027年10月30日正午です。"
    assert enriched.claims[-1].evidence_element_ids == (
        answer.date_calculations[0].evidence_element_ids
    )


def test_utc_suffix_is_treated_as_local_policy_cutoff_not_timezone_conversion() -> None:
    answer = parse_answer_output(
        _v2_answer(str(uuid4()), cutoff_time="12:00:00.000Z")
    )

    enriched = apply_date_calculations(answer)

    assert enriched.claims[-1].text == "提出期限は2027年10月30日正午です。"


def test_calendar_day_calculation_handles_leap_year_and_year_boundary() -> None:
    leap = parse_answer_output(
        _v2_answer(str(uuid4()), anchor_date="2028-02-28", offset_value=1)
    ).date_calculations[0]
    year_end = parse_answer_output(
        _v2_answer(
            str(uuid4()),
            anchor_date="2027-12-31",
            offset_value=1,
            counting_rule="anchor_day_is_day_1",
            cutoff_time=None,
        )
    ).date_calculations[0]

    assert calculate_deadline(leap) == (date(2028, 2, 29), time(12, 0))
    assert calculate_deadline(year_end) == (date(2027, 12, 31), None)


def test_v2_missing_condition_preserves_type_and_evidence() -> None:
    evidence_id = str(uuid4())
    data = _v2_answer(evidence_id)
    data["date_calculations"] = []
    data["missing_conditions"] = [
        {
            "type": "missing_document",
            "description": "書庫整理奨励金の規程",
            "evidence_element_ids": [],
        }
    ]

    answer = parse_answer_output(data)

    assert answer.missing_conditions[0].condition_type == "missing_document"
    assert answer.missing_conditions[0].description == "書庫整理奨励金の規程"


def test_v2_prompt_limits_missing_conditions_to_question_scope() -> None:
    prompt = build_answer_contract_v2_prompt("一覧は？", [], None)

    assert "質問が明示的に求める結論" in prompt
    assert "一般ルール、選択肢、項目一覧" in prompt
    assert "claimsも質問が明示的に求める対象と範囲" in prompt
    assert "別規程自体をmissing_documentへ入れない" in prompt
