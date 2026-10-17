"""Independent review regression for unsafe version-resolution promotion."""

from uuid import uuid4

import pytest


from src.answering import parse_answer_output
from src.classification_scope_contract import classify_scope_answer
from src.llm_provider import StructuredLLMResult

EID = "c55b0157-7719-41aa-a57e-2516327dac2b"


class Provider:
    provider_name = "fake"
    model = "fake"

    def __init__(self, data):
        self.data = data

    def generate_structured(self, prompt, schema):
        return StructuredLLMResult("fake", "fake", self.data)


class Logger:
    def __init__(self):
        self.events = []

    def record_classification_attempt(self, *args, **kwargs):
        self.events.append(kwargs)


@pytest.mark.parametrize(
    "mode", ["resolved", "low_confidence", "still_conflicting", "malformed"]
)
def test_resolver_must_not_promote_unresolved_price_claim_to_sufficient(mode):
    answer_data = {
        "schema_version": "1.0",
        "claims": [
            {
                "claim_id": "claim-1",
                "ordinal": 1,
                "text": "200円と300円が競合するため、適用単価を確定できません。",
                "evidence_element_ids": [EID],
                "evidence_kind": "text",
            }
        ],
        "missing_conditions": [],
    }
    classification = {
        "schema_version": "scope-2.0",
        "confidence": 0.9,
        "targets": [
            {
                "target": "適用単価",
                "intent": "general_rule",
                "evidence_sufficient": True,
                "evidence_ids": [EID],
                "claim_ids": ["claim-1"],
                "claim_support": "supported",
                "answer_complete": True,
                "reviews": [
                    {
                        "type": "version_conflict",
                        "reason": "適用単価が競合",
                        "evidence_ids": [EID],
                    }
                ],
            }
        ],
    }
    resolution = {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "version_conflict": False,
        "resolution_basis": "question_date",
        "evidence_element_ids": [EID],
        "confidence": 0.95,
        "error_code": None,
    }
    if mode == "low_confidence":
        resolution["confidence"] = 0.4
    elif mode == "still_conflicting":
        resolution.update(version_conflict=True, resolution_basis="unresolved")
    elif mode == "malformed":
        resolution.pop("confidence")
    logger = Logger()
    display, _, _, metadata = classify_scope_answer(
        question="2027年4月1日の適用単価はいくら？",
        evidence=[{"element_id": EID, "content": "2026年まで200円。2027年から300円。"}],
        answer=parse_answer_output(answer_data),
        answer_data=answer_data,
        classifier=Provider(classification),
        event_logger=logger,
        request_id=uuid4(),
        version_resolver=Provider(resolution),
        version_resolution_schema={},
    )
    assert not (display.status == "SUCCESS" and display.label == "根拠十分"), (
        "Resolving the document version does not repair an answer which still "
        f"claims the price cannot be determined: {display.text}; {metadata}"
    )

    if mode == "resolved":
        assert display.status == "GENERATION_INCOMPLETE"
        assert display.label is None
        assert not display.visible_claims
        assert display.invariant_code == "VERSION_REVALIDATION_FAILED"
        assert metadata["status"] == "REVALIDATION_FAILED"
    else:
        assert display.status == "SUCCESS" and display.label == "判断要"
    assert metadata["raw_output"] == resolution
    event = logger.events[0]
    assert event["prompt_version"] == "version-resolution-v1"
    assert event["factors"]["raw_output"] == resolution
    if mode == "malformed":
        assert metadata["status"] == "RESOLUTION_FAILED"
        assert metadata["fallback_used"]
        assert event["error_summary"]
    else:
        assert metadata["resolution_basis"] == resolution["resolution_basis"]
        assert metadata["confidence"] == resolution["confidence"]
        assert metadata["evidence_ids"] == [EID]
        assert event["confidence"] == resolution["confidence"]
    if mode == "low_confidence":
        assert metadata["status"] == "LOW_CONFIDENCE_FALLBACK"
        assert metadata["fallback_used"]
