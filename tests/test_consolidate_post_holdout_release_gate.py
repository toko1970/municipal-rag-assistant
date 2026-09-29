from eval.consolidate_post_holdout_release_gate import consolidate


def test_release_gate_reuses_unaffected_regression_and_requires_e2e_pass() -> None:
    result = consolidate(
        {
            "candidate": {"success": 120, "total": 130, "success_rate": 120 / 130},
            "impact_gate_passed": True,
        },
        {
            "summary": {
                "formal_changed_questions": 0,
                "formal_current_route_positive": 0,
            }
        },
        {
            "gate_passed": True,
            "logical_external_calls": 8,
            "estimated_cost_usd": 0.002,
        },
    )

    assert result["release_gate_passed"] is True
    assert result["development_regression"]["result_reused"] is True
    assert "上昇値ではない" in result["claim_boundary"]
