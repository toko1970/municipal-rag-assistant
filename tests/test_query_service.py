import hashlib
from uuid import uuid4

import pytest

from src.asset_store import VisualEvidenceAsset
from src.contracts import IndexableElement, SearchHit
from src.llm_provider import StructuredLLMResult
from src.query_service import answer_question


class FakeProvider:
    provider_name = "fake"
    model = "fake-model"

    def __init__(self, data: dict):
        self.data = data

    def generate_structured(self, _prompt: str, _schema: dict) -> StructuredLLMResult:
        return StructuredLLMResult("fake", self.model, self.data, 10, 5, 15)


class FakeMultimodalProvider(FakeProvider):
    def __init__(self, data: dict):
        super().__init__(data)
        self.media = None
        self.prompt = None

    def generate_structured_with_media(
        self, prompt: str, _schema: dict, *, media: list[tuple[bytes, str]]
    ) -> StructuredLLMResult:
        self.prompt = prompt
        self.media = media
        return StructuredLLMResult("fake", self.model, self.data, 12, 6, 18)


class FailingProvider:
    provider_name = "fake"
    model = "failing-model"

    def generate_structured(self, _prompt: str, _schema: dict):
        raise RuntimeError("provider unavailable")


class CountingProvider(FakeProvider):
    def __init__(self, response):
        super().__init__(response)
        self.calls = 0

    def generate_structured(self, prompt: str, schema: dict):
        self.calls += 1
        return super().generate_structured(prompt, schema)


class PromptCapturingProvider(FakeProvider):
    def __init__(self, response):
        super().__init__(response)
        self.prompt = None

    def generate_structured(self, prompt: str, schema: dict):
        self.prompt = prompt
        return super().generate_structured(prompt, schema)


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


def test_query_flow_keeps_generation_classification_and_display_separate() -> None:
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="給与条例",
        heading="支給日",
        content="給与は毎月21日に支給する。",
    )
    hit = SearchHit(element=element, score=0.9, rank=1)
    generator = FakeProvider(
        {
            "schema_version": "1.0",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "給与は毎月21日に支給されます。",
                    "evidence_element_ids": [str(element.id)],
                    "evidence_kind": "text",
                }
            ],
            "missing_conditions": [],
        }
    )
    classifier = FakeProvider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
                "requires_case_facts": False,
                "requires_policy_judgment": False,
                "version_conflict": False,
            },
            "confidence": 0.97,
            "error_code": None,
        }
    )
    logger = FakeLogger()

    result = answer_question(
        "給与支給日はいつですか？",
        embed_query=lambda _question: [1.0, 0.0, 0.0],
        vector_index=FakeIndex([hit]),
        generator=generator,
        classifier=classifier,
        event_logger=logger,
        answer_schema={"title": "answer"},
        classification_schema={"title": "classification"},
    )

    assert result["request_id"] == str(logger.request_id)
    assert result["answer_label"] == "根拠十分"
    assert [event[0] for event in logger.events] == [
        "request",
        "retrieval",
        "generation",
        "classification",
        "answer",
    ]
    assert logger.events[-1][2]["claims"][0]["evidence_element_ids"] == [element.id]


def test_query_flow_accepts_bounded_generation_prompt_candidate() -> None:
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="給与条例",
        heading="支給日",
        content="給与は毎月21日に支給する。",
    )
    generator = PromptCapturingProvider(
        {
            "schema_version": "1.0",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "給与は毎月21日に支給されます。",
                    "evidence_element_ids": [str(element.id)],
                    "evidence_kind": "text",
                }
            ],
            "missing_conditions": [],
        }
    )
    classifier = FakeProvider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
                "requires_case_facts": False,
                "requires_policy_judgment": False,
                "version_conflict": False,
            },
            "confidence": 0.97,
            "error_code": None,
        }
    )
    logger = FakeLogger()

    answer_question(
        "給与支給日はいつですか？",
        embed_query=lambda _question: [1.0],
        vector_index=FakeIndex([SearchHit(element, 0.9, 1)]),
        generator=generator,
        classifier=classifier,
        event_logger=logger,
        answer_schema={},
        classification_schema={},
        generation_prompt_builder=lambda question, _hits, _assets: (
            f"candidate: {question}"
        ),
        generation_prompt_version="answer-claims-required-facets-v1",
    )

    assert generator.prompt == "candidate: 給与支給日はいつですか？"
    generation_event = next(
        event for event in logger.events if event[0] == "generation"
    )
    assert generation_event[2]["prompt_version"] == "answer-claims-required-facets-v1"


def test_query_flow_keeps_model_case_fact_flag_without_missing_condition() -> None:
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="認定フロー",
        heading="判定",
        content="30分未満は認定対象外。",
    )
    generator = FakeProvider(
        {
            "schema_version": "1.0",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "30分未満は認定対象外です。",
                    "evidence_element_ids": [str(element.id)],
                    "evidence_kind": "flow_edge",
                }
            ],
            "missing_conditions": [],
        }
    )
    classifier = FakeProvider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
                "requires_case_facts": True,
                "requires_policy_judgment": False,
                "version_conflict": False,
            },
            "confidence": 0.95,
            "error_code": None,
        }
    )
    logger = FakeLogger()

    result = answer_question(
        "30分未満の場合は認定されますか？",
        embed_query=lambda _question: [1.0],
        vector_index=FakeIndex([SearchHit(element, 0.9, 1)]),
        generator=generator,
        classifier=classifier,
        event_logger=logger,
        answer_schema={},
        classification_schema={},
    )

    classification_event = next(
        event for event in logger.events if event[0] == "classification"
    )
    assert result["answer_label"] == "判断要"
    assert result["classification_decision_version"] == "classification-decision-v1"
    assert classification_event[2]["factors"]["requires_case_facts"] is True


def test_generation_failure_is_logged_separately() -> None:
    logger = FakeLogger()

    try:
        answer_question(
            "質問",
            embed_query=lambda _question: [1.0],
            vector_index=FakeIndex([]),
            generator=FailingProvider(),
            classifier=FailingProvider(),
            event_logger=logger,
            answer_schema={},
            classification_schema={},
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("generation failure was not raised")

    assert [event[0] for event in logger.events] == [
        "request",
        "retrieval",
        "generation",
    ]
    assert logger.events[-1][2]["status"] == "GENERATION_FAILED"


def test_classification_failure_is_logged_after_successful_generation() -> None:
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="文書",
        heading="見出し",
        content="本文",
    )
    generator = FakeProvider(
        {
            "schema_version": "1.0",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "主張",
                    "evidence_element_ids": [str(element.id)],
                    "evidence_kind": "text",
                }
            ],
            "missing_conditions": [],
        }
    )
    logger = FakeLogger()

    try:
        answer_question(
            "質問",
            embed_query=lambda _question: [1.0],
            vector_index=FakeIndex([SearchHit(element, 0.9, 1)]),
            generator=generator,
            classifier=FailingProvider(),
            event_logger=logger,
            answer_schema={},
            classification_schema={},
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("classification failure was not raised")

    assert [event[0] for event in logger.events] == [
        "request",
        "retrieval",
        "generation",
        "classification",
    ]
    assert logger.events[-1][2]["status"] == "CLASSIFICATION_FAILED"


def test_display_contract_failure_preserves_classification_factors() -> None:
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="文書",
        heading="見出し",
        content="本文",
    )
    generator = FakeProvider(
        {
            "schema_version": "1.0",
            "claims": [],
            "missing_conditions": ["別規程"],
        }
    )
    classifier = FakeProvider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
                "requires_case_facts": False,
                "requires_policy_judgment": False,
                "version_conflict": False,
            },
            "confidence": 0.9,
            "error_code": None,
        }
    )
    logger = FakeLogger()

    with pytest.raises(ValueError, match="表示条件"):
        answer_question(
            "質問",
            embed_query=lambda _question: [1.0],
            vector_index=FakeIndex([SearchHit(element, 0.9, 1)]),
            generator=generator,
            classifier=classifier,
            event_logger=logger,
            answer_schema={},
            classification_schema={},
        )

    event = logger.events[-1][2]
    assert event["status"] == "CLASSIFICATION_FAILED"
    assert event["derived_label"] == "根拠十分"
    assert event["factors"]["retrieval_sufficient"] is True


def test_visual_hit_uses_verified_image_and_returns_display_metadata(tmp_path) -> None:
    content = b"verified-png"
    path = tmp_path / "page.png"
    path.write_bytes(content)
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="通勤手当申請処理フロー",
        heading="申請フロー",
        content="不備ありの場合は申請者へ差し戻す。",
        element_type="flowchart",
        page_number=1,
        metadata={
            "visual_extraction": {"nodes": [{"id": "n1", "text": "申請者へ差戻し"}]}
        },
    )
    asset = VisualEvidenceAsset(
        element_id=element.id,
        storage_uri=path.as_uri(),
        mime_type="image/png",
        page_number=1,
        sha256=hashlib.sha256(content).hexdigest(),
        bbox={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
    )
    generator = FakeMultimodalProvider(
        {
            "schema_version": "1.0",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "不備がある場合は申請者へ差し戻します。",
                    "evidence_element_ids": [str(element.id)],
                    "evidence_kind": "flow_edge",
                }
            ],
            "missing_conditions": [],
        }
    )
    classifier = FakeProvider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
                "requires_case_facts": False,
                "requires_policy_judgment": False,
                "version_conflict": False,
            },
            "confidence": 0.9,
            "error_code": None,
        }
    )

    result = answer_question(
        "申請に不備がある場合はどうなりますか？",
        embed_query=lambda _question: [1.0],
        vector_index=FakeIndex([SearchHit(element, 0.9, 1)]),
        generator=generator,
        classifier=classifier,
        event_logger=FakeLogger(),
        answer_schema={},
        classification_schema={},
        visual_asset_loader=lambda ids: [asset] if element.id in ids else [],
    )

    assert generator.media == [(content, "image/png")]
    assert "申請者へ差戻し" in generator.prompt
    visual = result["references"][0]["visual_asset"]
    assert visual["content"] == content
    assert visual["page_number"] == 1


def test_visual_hash_mismatch_is_logged_as_generation_failure(tmp_path) -> None:
    path = tmp_path / "page.png"
    path.write_bytes(b"changed")
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="図表",
        heading="図表",
        content="図表内容",
        element_type="table",
    )
    asset = VisualEvidenceAsset(
        element_id=element.id,
        storage_uri=path.as_uri(),
        mime_type="image/png",
        page_number=1,
        sha256="0" * 64,
    )
    logger = FakeLogger()

    try:
        answer_question(
            "図表の質問",
            embed_query=lambda _question: [1.0],
            vector_index=FakeIndex([SearchHit(element, 0.9, 1)]),
            generator=FakeMultimodalProvider({}),
            classifier=FakeProvider({}),
            event_logger=logger,
            answer_schema={},
            classification_schema={},
            visual_asset_loader=lambda _ids: [asset],
        )
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("hash mismatch was not raised")

    assert logger.events[-1][0] == "generation"
    assert logger.events[-1][2]["status"] == "GENERATION_FAILED"


def _version_resolution_response(
    element_id, *, conflict: bool, basis: str, confidence: float
) -> dict:
    return {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "version_conflict": conflict,
        "resolution_basis": basis,
        "evidence_element_ids": [str(element_id)],
        "confidence": confidence,
        "error_code": None,
    }


def _run_version_resolution(
    *,
    baseline_conflict: bool,
    resolver,
    missing_conditions=None,
):
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="制度改正通知",
        heading="適用期間",
        content="2025年10月1日から新版を適用する。",
    )
    generator = FakeProvider(
        {
            "schema_version": "1.0",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": "2025年10月は新版を適用します。",
                    "evidence_element_ids": [str(element.id)],
                    "evidence_kind": "text",
                }
            ],
            "missing_conditions": missing_conditions or [],
        }
    )
    classifier = FakeProvider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
                "requires_case_facts": False,
                "requires_policy_judgment": False,
                "version_conflict": baseline_conflict,
            },
            "confidence": 0.9,
            "error_code": None,
        }
    )
    logger = FakeLogger()
    result = answer_question(
        "2025年10月はどの版を適用しますか？",
        embed_query=lambda _question: [1.0],
        vector_index=FakeIndex([SearchHit(element, 0.9, 1)]),
        generator=generator,
        classifier=classifier,
        event_logger=logger,
        answer_schema={},
        classification_schema={},
        version_resolver=resolver,
        version_resolution_schema={},
    )
    return result, logger, element


def test_version_resolver_is_not_called_without_baseline_conflict() -> None:
    resolver = CountingProvider({})

    result, logger, _element = _run_version_resolution(
        baseline_conflict=False,
        resolver=resolver,
    )

    assert resolver.calls == 0
    assert result["answer_label"] == "根拠十分"
    assert result["version_resolution"]["status"] == "NOT_REQUIRED"
    classification_events = [
        event for event in logger.events if event[0] == "classification"
    ]
    assert len(classification_events) == 1


def test_version_resolver_replaces_only_version_factor() -> None:
    class SuccessfulResolver:
        provider_name = "fake"
        model = "fake-model"

        def generate_structured(self, prompt: str, _schema: dict):
            element_id = prompt.split('"element_id": "', 1)[1].split('"', 1)[0]
            data = _version_resolution_response(
                element_id,
                conflict=False,
                basis="effective_period",
                confidence=1.0,
            )
            return StructuredLLMResult("fake", self.model, data, 10, 5, 15)

    result, logger, _ = _run_version_resolution(
        baseline_conflict=True,
        resolver=SuccessfulResolver(),
    )

    assert result["answer_label"] == "根拠十分"
    assert result["version_resolution"]["status"] == "SUCCESS"
    assert result["version_resolution"]["applied"] is True
    classification_events = [
        event for event in logger.events if event[0] == "classification"
    ]
    assert classification_events[0][2]["status"] == "SUCCESS"
    assert classification_events[1][2]["factors"]["version_conflict"] is False


def test_version_resolver_low_confidence_and_display_contract_use_fallback() -> None:
    class ResolverForRetrievedElement:
        provider_name = "fake"
        model = "fake-model"

        def __init__(self, *, confidence: float):
            self.confidence = confidence

        def generate_structured(self, prompt: str, _schema: dict):
            element_id = prompt.split('"element_id": "', 1)[1].split('"', 1)[0]
            data = _version_resolution_response(
                element_id,
                conflict=False,
                basis="effective_period",
                confidence=self.confidence,
            )
            return StructuredLLMResult("fake", self.model, data, 10, 5, 15)

    low_result, low_logger, _ = _run_version_resolution(
        baseline_conflict=True,
        resolver=ResolverForRetrievedElement(confidence=0.5),
    )
    contract_result, contract_logger, _ = _run_version_resolution(
        baseline_conflict=True,
        resolver=ResolverForRetrievedElement(confidence=1.0),
        missing_conditions=["住居届の提出状況"],
    )

    assert low_result["answer_label"] == "判断要"
    assert low_result["version_resolution"]["status"] == "LOW_CONFIDENCE_FALLBACK"
    low_classification = [
        event for event in low_logger.events if event[0] == "classification"
    ]
    assert low_classification[-1][2]["fallback_used"] is True
    assert contract_result["answer_label"] == "判断要"
    assert (
        contract_result["version_resolution"]["status"] == "DISPLAY_CONTRACT_FALLBACK"
    )
    contract_classification = [
        event for event in contract_logger.events if event[0] == "classification"
    ]
    assert contract_classification[-1][2]["fallback_used"] is True


def test_version_resolver_provider_failure_keeps_baseline_result() -> None:
    result, logger, _ = _run_version_resolution(
        baseline_conflict=True,
        resolver=FailingProvider(),
    )

    assert result["answer_label"] == "判断要"
    assert result["version_resolution"]["status"] == "RESOLUTION_FAILED"
    assert result["version_resolution"]["fallback_used"] is True
    classification_events = [
        event for event in logger.events if event[0] == "classification"
    ]
    assert classification_events[0][2]["status"] == "RESOLUTION_FAILED"
    assert classification_events[-1][2]["factors"]["version_conflict"] is True


def test_version_resolver_rejects_evidence_outside_retrieved_hits() -> None:
    class ResolverWithUnknownEvidence:
        provider_name = "fake"
        model = "fake-model"

        def generate_structured(self, _prompt: str, _schema: dict):
            data = _version_resolution_response(
                uuid4(),
                conflict=False,
                basis="effective_period",
                confidence=1.0,
            )
            return StructuredLLMResult("fake", self.model, data, 10, 5, 15)

    result, logger, _ = _run_version_resolution(
        baseline_conflict=True,
        resolver=ResolverWithUnknownEvidence(),
    )

    assert result["answer_label"] == "判断要"
    assert result["version_resolution"]["status"] == "RESOLUTION_FAILED"
    classification_events = [
        event for event in logger.events if event[0] == "classification"
    ]
    assert "取得外" in classification_events[0][2]["error_summary"]
    assert classification_events[-1][2]["fallback_used"] is True
