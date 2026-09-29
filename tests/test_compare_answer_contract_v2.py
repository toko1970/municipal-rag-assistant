from eval.compare_answer_contract_v2 import SCENARIOS, _content_ok, _contract_ok


def test_pilot_has_bounded_balanced_scope() -> None:
    assert len(SCENARIOS) == 12
    assert sum(item["group"] == "date" for item in SCENARIOS) == 6
    assert sum(item["group"] == "condition" for item in SCENARIOS) == 4
    assert sum(item["group"] == "control" for item in SCENARIOS) == 2
    assert len({item["id"] for item in SCENARIOS}) == len(SCENARIOS)


def test_candidate_contract_checks_expected_date_and_condition_types() -> None:
    date_case = SCENARIOS[0]
    condition_case = next(
        item for item in SCENARIOS if item["condition_type"] == "missing_document"
    )

    assert _contract_ok(
        date_case,
        "candidate",
        {"date_calculations": [{"calculation_id": "date-1"}], "missing_conditions": []},
    )
    assert _contract_ok(
        condition_case,
        "candidate",
        {
            "date_calculations": [],
            "missing_conditions": [{"type": "missing_document"}],
        },
    )


def test_content_rules_require_concrete_result() -> None:
    assert _content_ok("提出期限は2027年10月30日正午です。", SCENARIOS[0]["required"])
    assert not _content_ok(
        "提出期限は翌日を1日目とした20暦日目です。",
        SCENARIOS[0]["required"],
    )
