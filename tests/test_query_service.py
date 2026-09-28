import hashlib
from uuid import uuid4

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
    assert result["classification_decision_version"] == "classification-decision-v2"
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
