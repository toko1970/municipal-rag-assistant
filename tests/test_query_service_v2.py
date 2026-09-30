from uuid import uuid4

import pytest

from src.contracts import IndexableElement, SearchHit
from src.llm_provider import StructuredLLMResult
from src.query_service_v2 import (
    CLASSIFICATION_DECISION_V2_VERSION,
    CLASSIFICATION_PROMPT_V2_VERSION,
    QUESTION_CONTRACT_PROMPT_VERSION,
    answer_question_v2,
)


class FakeProvider:
    provider_name = "fake"
    model = "fake-model"

    def __init__(self, data: dict):
        self.data = data
        self.prompt = None
        self.calls = 0

    def generate_structured(self, prompt: str, _schema: dict) -> StructuredLLMResult:
        self.calls += 1
        self.prompt = prompt
        return StructuredLLMResult("fake", self.model, self.data, 10, 5, 15)


class FakeIndex:
    def __init__(self, hits):
        self.hits = hits

    def search(self, _vector, limit):
        return self.hits[:limit]


class FakeLogger:
    def __init__(self):
        self.request_id = uuid4()
        self.events = []

    def start_request(self, question):
        self.events.append(("request", question))
        return self.request_id

    def record_retrieval(self, request_id, hits):
        self.events.append(("retrieval", request_id, len(hits)))

    def record_generation_attempt(self, request_id, **kwargs):
        self.events.append(("generation", request_id, kwargs))
        return uuid4()

    def record_classification_attempt(self, request_id, **kwargs):
        self.events.append(("classification", request_id, kwargs))
        return uuid4()

    def record_answer_result(self, request_id, **kwargs):
        self.events.append(("answer", request_id, kwargs))
        return uuid4()


def _hit():
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="制度通知",
        heading="支給日",
        content="給与は毎月21日に支給する。",
    )
    return SearchHit(element=element, score=0.9, rank=1)


def _contract() -> dict:
    return {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "requested_facets": [
            {
                "facet_id": "facet-1",
                "requirement": "給与支給日",
                "answer_type": "date",
            }
        ],
        "input_facts": [],
        "error_code": None,
    }


def _answer(evidence_id: str, *, with_claim: bool = True) -> dict:
    claims = []
    if with_claim:
        claims.append(
            {
                "claim_id": "claim-1",
                "ordinal": 1,
                "text": "給与は毎月21日に支給されます。",
                "facet_ids": ["facet-1"],
                "input_fact_ids": [],
                "calculation_ids": [],
                "evidence_element_ids": [evidence_id],
                "evidence_kind": "text",
            }
        )
    return {
        "schema_version": "3.0-candidate",
        "claims": claims,
        "missing_conditions": [],
        "date_calculations": [],
    }


def _classification(
    evidence_id: str,
    *,
    claim_ids=("claim-1",),
    claim_support="fully_supported",
    reviews=None,
) -> dict:
    return {
        "schema_version": "2.0-candidate",
        "status": "SUCCESS",
        "facet_assessments": [
            {
                "facet_id": "facet-1",
                "claim_ids": list(claim_ids),
                "claim_support": claim_support,
                "evidence_coverage": "sufficient",
                "human_review_requirements": reviews or [],
                "evidence_element_ids": [evidence_id],
                "confidence": 0.95,
            }
        ],
        "confidence": 0.95,
        "error_code": None,
    }


def _run(
    *,
    contract=None,
    answer=None,
    classification=None,
    resolver=None,
    hit=None,
    logger=None,
    threshold=0.80,
):
    hit = hit or _hit()
    contract_provider = FakeProvider(contract or _contract())
    generator = FakeProvider(answer or _answer(str(hit.element.id)))
    classifier = FakeProvider(classification or _classification(str(hit.element.id)))
    logger = logger or FakeLogger()
    result = answer_question_v2(
        "給与支給日はいつですか？",
        embed_query=lambda _question: [1.0],
        vector_index=FakeIndex([hit]),
        question_contract_provider=contract_provider,
        generator=generator,
        classifier=classifier,
        event_logger=logger,
        question_contract_schema={},
        answer_schema={},
        classification_schema={},
        version_resolver=resolver,
        version_resolution_schema={} if resolver else None,
        version_resolution_confidence_threshold=threshold,
    )
    return result, logger, hit, contract_provider, generator, classifier


def test_v2_query_flow_uses_contract_and_logs_versioned_factors() -> None:
    result, logger, _hit_value, contract_provider, _generator, classifier = _run()

    assert result["answer_label"] == "根拠十分"
    assert (
        result["classification_decision_version"] == CLASSIFICATION_DECISION_V2_VERSION
    )
    assert "question-contract-v1" in contract_provider.prompt
    assert "最終ラベルではなく" in classifier.prompt
    classification_events = [row for row in logger.events if row[0] == "classification"]
    assert (
        classification_events[0][2]["prompt_version"]
        == QUESTION_CONTRACT_PROMPT_VERSION
    )
    assert (
        classification_events[-1][2]["prompt_version"]
        == CLASSIFICATION_PROMPT_V2_VERSION
    )
    assert (
        classification_events[-1][2]["factors"]["decision_version"]
        == CLASSIFICATION_DECISION_V2_VERSION
    )
    assert classification_events[-1][2]["factors"]["question_contract"] == _contract()


def test_v2_generation_incomplete_hides_partial_answer() -> None:
    hit = _hit()
    result, logger, *_rest = _run(
        hit=hit,
        answer=_answer(str(hit.element.id), with_claim=False),
        classification=_classification(
            str(hit.element.id), claim_ids=(), claim_support="no_claim"
        ),
    )

    assert result["answer_status"] == "GENERATION_INCOMPLETE"
    assert result["answer_label"] is None
    assert result["claims"] == []
    assert logger.events[-1][2]["label"] is None


def test_v2_unknown_claim_reference_fails_closed() -> None:
    hit = _hit()
    result, logger, *_rest = _run(
        hit=hit,
        answer=_answer(str(hit.element.id)),
        classification=_classification(str(hit.element.id), claim_ids=("claim-2",)),
    )

    assert result["answer_status"] == "PIPELINE_INCONSISTENCY"
    assert result["invariant_code"] == "UNKNOWN_CLAIM"
    assert result["answer_label"] is None
    final_classification = [row for row in logger.events if row[0] == "classification"][
        -1
    ]
    assert final_classification[2]["derived_label"] is None


def test_v2_contract_failure_is_logged_and_stops_before_generation() -> None:
    failed_contract = {
        "schema_version": "1.0",
        "status": "CONTRACT_FAILED",
        "requested_facets": [],
        "input_facts": [],
        "error_code": "NO_FACET",
    }

    logger = FakeLogger()

    with pytest.raises(ValueError, match="NO_FACET"):
        _run(contract=failed_contract, logger=logger)

    assert [event[0] for event in logger.events] == ["request", "classification"]
    assert logger.events[-1][2]["status"] == "CONTRACT_FAILED"
    assert logger.events[-1][2]["derived_label"] is None


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_v2_rejects_invalid_version_resolution_threshold(threshold: float) -> None:
    with pytest.raises(ValueError, match="0以上1以下"):
        _run(threshold=threshold)


def test_version_resolver_changes_only_version_requirement() -> None:
    hit = _hit()
    evidence_id = str(hit.element.id)
    answer = _answer(evidence_id)
    answer["missing_conditions"] = [
        {
            "condition_id": "condition-1",
            "type": "version_conflict",
            "description": "適用版",
            "facet_ids": ["facet-1"],
            "evidence_element_ids": [evidence_id],
        },
        {
            "condition_id": "condition-2",
            "type": "case_fact",
            "description": "個別記録",
            "facet_ids": ["facet-1"],
            "evidence_element_ids": [evidence_id],
        },
    ]
    reviews = [
        {
            "review_id": "review-1",
            "type": "version_conflict",
            "description": "適用版",
            "condition_ids": ["condition-1"],
            "evidence_element_ids": [evidence_id],
        },
        {
            "review_id": "review-2",
            "type": "case_fact",
            "description": "個別記録",
            "condition_ids": ["condition-2"],
            "evidence_element_ids": [evidence_id],
        },
    ]
    resolver = FakeProvider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "version_conflict": False,
            "resolution_basis": "effective_period",
            "evidence_element_ids": [evidence_id],
            "confidence": 0.99,
            "error_code": None,
        }
    )

    result, logger, *_rest = _run(
        hit=hit,
        answer=answer,
        classification=_classification(evidence_id, reviews=reviews),
        resolver=resolver,
    )

    assert result["answer_label"] == "判断要"
    assert "個別記録" in result["answer"]
    assert "適用版" not in result["answer"]
    assert resolver.calls == 1
    final_factors = [row for row in logger.events if row[0] == "classification"][-1][2][
        "factors"
    ]
    remaining = final_factors["facet_assessments"][0]["human_review_requirements"]
    assert [row["type"] for row in remaining] == ["case_fact"]


def test_version_resolver_is_not_called_for_incomplete_generation() -> None:
    hit = _hit()
    evidence_id = str(hit.element.id)
    answer = _answer(evidence_id)
    answer["missing_conditions"] = [
        {
            "condition_id": "condition-1",
            "type": "version_conflict",
            "description": "適用版",
            "facet_ids": ["facet-1"],
            "evidence_element_ids": [evidence_id],
        }
    ]
    reviews = [
        {
            "review_id": "review-1",
            "type": "version_conflict",
            "description": "適用版",
            "condition_ids": ["condition-1"],
            "evidence_element_ids": [evidence_id],
        }
    ]
    resolver = FakeProvider({})

    result, *_rest = _run(
        hit=hit,
        answer=answer,
        classification=_classification(
            evidence_id,
            claim_support="unsupported",
            reviews=reviews,
        ),
        resolver=resolver,
    )

    assert result["answer_status"] == "GENERATION_INCOMPLETE"
    assert result["version_resolution"]["status"] == "NOT_REQUIRED"
    assert resolver.calls == 0
