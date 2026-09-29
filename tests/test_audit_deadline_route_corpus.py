from eval.audit_deadline_route_corpus import audit, legacy_route


def test_legacy_route_reproduces_previous_boundary() -> None:
    assert legacy_route("2027年10月10日に受験。期限は何日まで？")
    assert not legacy_route("2027-10-10に受験。期限日はいつ？")


def test_audit_counts_formal_impact_separately() -> None:
    result = audit(
        [
            {
                "question_id": "Q001",
                "scenario_id": "S001",
                "variant_type": "formal",
                "question": "2027年10月10日に受験。期限は何日まで？",
            },
            {
                "question_id": "Q002",
                "scenario_id": "S001",
                "variant_type": "noisy",
                "question": "2027年10月10日の支給額は？",
            },
        ]
    )

    assert result["summary"]["questions"] == 2
    assert result["summary"]["formal_questions"] == 1
    assert result["summary"]["formal_changed_questions"] == 0
