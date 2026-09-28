from uuid import uuid4

from eval.analyze_version_resolver_regression import analyze


def _baseline_row(item_id: str, expected: str) -> dict:
    return {
        "id": item_id,
        "modality": "text",
        "primary_cause": "classification_failure",
        "retrieval_ok": True,
        "expected_label": expected,
        "candidate_label": "判断要",
        "candidate_classification_ok": expected == "判断要",
        "previous_decision_label": "判断要",
        "previous_decision_classification_ok": expected == "判断要",
        "error": None,
    }


def _text_record(item_id: str, *, missing: list[str]) -> dict:
    element_id = str(uuid4())
    return {
        "question_id": item_id,
        "classification_factors": {
            "retrieval_sufficient": True,
            "answer_fully_supported": True,
            "requires_case_facts": False,
            "requires_policy_judgment": False,
            "version_conflict": True,
        },
        "claims": [
            {
                "claim_id": "claim-1",
                "ordinal": 1,
                "text": "新版を適用します。",
                "evidence_element_ids": [element_id],
            }
        ],
        "missing_conditions": missing,
    }


def _resolver_record(item_id: str, element_id: str) -> dict:
    return {
        "question_id": item_id,
        "error": None,
        "response": {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "version_conflict": False,
            "resolution_basis": "effective_period",
            "evidence_element_ids": [element_id],
            "confidence": 1.0,
            "error_code": None,
        },
    }


def test_analyze_applies_safe_resolution_and_falls_back_on_display_contract() -> None:
    safe = _text_record("Q-SAFE", missing=[])
    fallback = _text_record("Q-FALLBACK", missing=["届出状況"])
    text = {"Q-SAFE": safe, "Q-FALLBACK": fallback}
    resolver = {
        item_id: _resolver_record(
            item_id, record["claims"][0]["evidence_element_ids"][0]
        )
        for item_id, record in text.items()
    }
    baseline = {
        "ledger": [
            _baseline_row("Q-SAFE", "根拠十分"),
            _baseline_row("Q-FALLBACK", "根拠十分"),
        ]
    }

    result = analyze(baseline, text, resolver)

    assert result["summary"]["candidate_primary_causes"] == {
        "classification_failure": 1,
        "success": 1,
    }
    assert result["summary"]["resolver_statuses"] == {
        "DISPLAY_CONTRACT_FALLBACK": 1,
        "SUCCESS": 1,
    }
    assert result["summary"]["classification_improvements"] == ["Q-SAFE"]
    assert result["summary"]["gate"]["passed"] is True
