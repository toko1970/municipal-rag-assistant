from types import SimpleNamespace
from uuid import uuid4
import pytest

from src.asset_store import VisualEvidenceAsset
from src.contracts import IndexableElement, SearchHit
from src.simple_rag_flow import generate_simple_qdrant_answer
from src.freeform_prompt_candidate import (
    EXPECTED_PROMPT_CONFIG_SHA256,
    PROMPT_CONFIG_SHA256,
    verify_prompt_config,
)


class FakeIndex:
    def __init__(self, hits):
        self.hits = hits
        self.queries = []

    def search(self, vector, limit):
        self.queries.append((vector, limit))
        return self.hits[:limit]


class FakeGenerator:
    model = "gemini-3.8-flash"
    provider_name = "gemini"

    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(
            text="回答分類: 根拠十分\n\n回答:\n規程の対象です。",
            metadata=lambda: {"model": self.model, "input_tokens": 10},
        )


class FakeEventLogger:
    def __init__(self):
        self.request_id = uuid4()
        self.events = []

    def start_request(self, question):
        self.events.append(("request", question))
        return self.request_id

    def record_retrieval(self, request_id, hits):
        self.events.append(("retrieval", request_id, hits))

    def record_generation_attempt(self, request_id, **kwargs):
        self.events.append(("generation", request_id, kwargs))

    def record_answer_result(self, request_id, **kwargs):
        self.events.append(("answer", request_id, kwargs))


def test_simple_qdrant_flow_retrieves_then_generates_once(monkeypatch):
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="給与制度規程",
        heading="適用対象",
        content="常勤職員に適用する。",
        metadata={
            "document_key": "DOC-001",
            "source": "01_salary_rules.md",
            "ordinal": 3,
            "effective_date": "2025-04-01",
            "version": "1.0",
            "document_role": "primary",
            "is_primary": True,
            "content_hash": "a" * 64,
        },
    )
    index = FakeIndex([SearchHit(element=element, score=0.12, rank=1)])
    generator = FakeGenerator()
    query_vectors = []

    def embed(query):
        query_vectors.append(query)
        return [0.1, 0.2]

    monkeypatch.setattr("src.simple_rag_flow.TOP_K", 8)
    result = generate_simple_qdrant_answer(
        "常勤職員に適用されますか？",
        embed_query=embed,
        vector_index=index,
        generator=generator,
        record_log=False,
    )

    assert len(generator.prompts) == 1
    assert "常勤職員に適用する。" in generator.prompts[0]
    assert "常勤職員に適用されますか？" in generator.prompts[0]
    assert result["answer"].startswith("回答分類: 根拠十分")
    assert result["references"][0]["document_id"] == "DOC-001"
    assert result["references"][0]["content"] == "常勤職員に適用する。"
    assert result["references"][0]["source"] == "01_salary_rules.md"
    assert result["references"][0]["version_id"] == str(element.version_id)
    assert result["references"][0]["effective_date"] == "2025-04-01"
    assert result["references"][0]["version"] == "1.0"
    assert result["references"][0]["document_role"] == "primary"
    assert result["references"][0]["is_primary"] is True
    assert result["references"][0]["content_hash"] == "a" * 64
    assert len(query_vectors) == 1
    assert index.queries == [([0.1, 0.2], 8)]


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "  \n",
        "回答だけで分類なし",
        "回答分類: 根拠十分\n回答:\n\n根拠文書:",
        "回答分類: 根拠十分\n回答分類: 文書不足\n回答: 矛盾",
    ],
)
def test_incomplete_freeform_output_is_not_success(answer):
    class OutputGenerator(FakeGenerator):
        def generate(self, _prompt):
            return SimpleNamespace(text=answer, metadata=lambda: {})

    result = generate_simple_qdrant_answer(
        "質問", retrieved_hits=[], generator=OutputGenerator(), record_log=False
    )

    assert result["answer_status"] == "GENERATION_INCOMPLETE"
    assert result["degraded"] is True
    assert result["answer_label"] is None
    assert "確認できませんでした" in result["answer"]


@pytest.mark.parametrize(
    "classification_line",
    [
        "回答分類: 根拠十分",
        "回答分類： 根拠十分",
        "回答分類:\n（根拠十分）",
    ],
)
def test_freeform_label_accepts_supported_colon_variants(classification_line):
    class OutputGenerator(FakeGenerator):
        def generate(self, _prompt):
            return SimpleNamespace(
                text=f"{classification_line}\n回答:\n根拠があります。",
                metadata=lambda: {},
            )

    result = generate_simple_qdrant_answer(
        "質問", retrieved_hits=[], generator=OutputGenerator(), record_log=False
    )
    assert result["answer_status"] == "SUCCESS"
    assert result["answer_label"] == "根拠十分"


def test_explicit_provider_truncation_is_not_success():
    class TruncatedGenerator(FakeGenerator):
        def generate(self, _prompt):
            return SimpleNamespace(
                text="回答分類: 根拠十分\n回答:\n途中までの回答",
                metadata=lambda: {"finish_reason": "MAX_TOKENS"},
            )

    result = generate_simple_qdrant_answer(
        "質問", retrieved_hits=[], generator=TruncatedGenerator(), record_log=False
    )
    assert result["answer_status"] == "GENERATION_INCOMPLETE"
    assert result["answer_label"] is None


def test_autoresearch_candidate_prompt_hash_is_frozen():
    assert PROMPT_CONFIG_SHA256 == EXPECTED_PROMPT_CONFIG_SHA256
    assert verify_prompt_config() == EXPECTED_PROMPT_CONFIG_SHA256


def test_autoresearch_candidate_route_uses_frozen_freeform_prompt():
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="旅費規程",
        heading="宿泊費",
        content="朝食相当額1,000円を控除する。",
        metadata={"document_key": "DOC-002", "ordinal": 1},
    )
    hit = SearchHit(element=element, score=0.1, rank=1)
    generator = FakeGenerator()
    result = generate_simple_qdrant_answer(
        "朝食付きの場合の宿泊費を教えてください。",
        retrieved_hits=[hit],
        generator=generator,
        record_log=False,
        prompt_variant="autoresearch_candidate",
    )
    assert len(generator.prompts) == 1
    assert "表や図表に質問に関係する備考、上限、例外条件" in generator.prompts[0]
    assert "朝食相当額1,000円を控除する。" in generator.prompts[0]
    assert result["prompt_variant"] == "autoresearch_candidate"


def test_candidate_route_records_answer_and_feedback_request_id(monkeypatch):
    element = IndexableElement(
        id=uuid4(), document_id=uuid4(), version_id=uuid4(),
        document_name="給与規程", heading="対象", content="常勤職員。",
        metadata={"document_key": "DOC-003", "ordinal": 1},
    )
    hit = SearchHit(element=element, score=0.1, rank=1)
    event_logger = FakeEventLogger()
    result = generate_simple_qdrant_answer(
        "誰が対象ですか？", retrieved_hits=[hit], generator=FakeGenerator(),
        prompt_variant="autoresearch_candidate", event_logger=event_logger,
    )

    assert result["request_id"] == str(event_logger.request_id)
    assert [event[0] for event in event_logger.events] == [
        "request", "retrieval", "generation", "answer"
    ]
    generation = event_logger.events[2][2]
    assert generation["status"] == "SUCCESS"
    assert generation["prompt_version"].startswith("freeform-candidate:")
    assert generation["response_data"] is None
    assert event_logger.events[3][2]["display_text"] == result["answer"]
    assert event_logger.events[3][2]["claims"] == []


def test_candidate_route_records_failed_generation_then_reraises():
    class BrokenGenerator(FakeGenerator):
        def generate(self, _prompt):
            raise RuntimeError("provider credentials should not be logged")

    event_logger = FakeEventLogger()
    element = IndexableElement(
        id=uuid4(), document_id=uuid4(), version_id=uuid4(),
        document_name="給与規程", heading="対象", content="常勤職員。",
        metadata={"document_key": "DOC-004", "ordinal": 1},
    )
    hit = SearchHit(element=element, score=0.1, rank=1)
    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "誰が対象ですか？", retrieved_hits=[hit], generator=BrokenGenerator(),
            prompt_variant="autoresearch_candidate", event_logger=event_logger,
        )

    generation = event_logger.events[-2][2]
    assert generation["status"] == "FAILED"
    assert generation["error_summary"] == "RuntimeError"
    assert "credentials" not in generation["error_summary"]
    assert event_logger.events[-1][2]["status"] == "GENERATION_FAILED"


def test_retrieval_failure_is_recorded_without_generation_attempt():
    event_logger = FakeEventLogger()

    def broken_embedding(_query):
        raise RuntimeError("private provider detail")

    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "質問",
            embed_query=broken_embedding,
            vector_index=FakeIndex([]),
            generator=FakeGenerator(),
            event_logger=event_logger,
        )

    assert [event[0] for event in event_logger.events] == ["request", "answer"]
    assert event_logger.events[-1][2]["status"] == "EMBEDDING_FAILED"
    assert "private provider detail" not in event_logger.events[-1][2]["display_text"]


def test_qdrant_search_failure_is_recorded_at_retrieval_stage():
    class BrokenIndex(FakeIndex):
        def search(self, _vector, _limit):
            raise RuntimeError("private Qdrant detail")

    event_logger = FakeEventLogger()
    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "質問",
            embed_query=lambda _query: [0.1],
            vector_index=BrokenIndex([]),
            generator=FakeGenerator(),
            event_logger=event_logger,
        )

    assert event_logger.events[-1][2]["status"] == "RETRIEVAL_FAILED"
    assert not any(event[0] == "generation" for event in event_logger.events)


def test_retrieval_record_failure_is_not_mislabeled_as_generation():
    class BrokenEventLogger(FakeEventLogger):
        def record_retrieval(self, _request_id, _hits):
            raise RuntimeError("private persistence detail")

    event_logger = BrokenEventLogger()
    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "質問", retrieved_hits=[], generator=FakeGenerator(),
            event_logger=event_logger,
        )

    assert event_logger.events[-1][2]["status"] == "RETRIEVAL_RECORD_FAILED"
    assert not any(event[0] == "generation" for event in event_logger.events)


def test_context_build_failure_is_recorded_without_generation_attempt(monkeypatch):
    event_logger = FakeEventLogger()
    monkeypatch.setattr(
        "src.simple_rag_flow.build_context",
        lambda _documents: (_ for _ in ()).throw(RuntimeError("context detail")),
    )

    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "質問",
            retrieved_hits=[],
            generator=FakeGenerator(),
            event_logger=event_logger,
        )

    assert event_logger.events[-1][2]["status"] == "CONTEXT_BUILD_FAILED"
    assert not any(event[0] == "generation" for event in event_logger.events)


def test_generator_setup_failure_is_recorded_without_generation_attempt(monkeypatch):
    event_logger = FakeEventLogger()

    def broken_generator(*_args, **_kwargs):
        raise RuntimeError("private provider setup detail")

    monkeypatch.setattr("src.simple_rag_flow.GeminiProvider", broken_generator)
    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "質問", retrieved_hits=[], event_logger=event_logger
        )

    assert event_logger.events[-1][2]["status"] == "GENERATOR_SETUP_FAILED"
    assert not any(event[0] == "generation" for event in event_logger.events)


def test_visual_metadata_failure_is_recorded_before_generation():
    event_logger = FakeEventLogger()
    element = IndexableElement(
        id=uuid4(), document_id=uuid4(), version_id=uuid4(),
        document_name="規程", heading="表", content="表を参照",
    )
    hit = SearchHit(element=element, score=0.1, rank=1)

    def broken_loader(_element_ids):
        raise RuntimeError("private metadata detail")

    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "質問", retrieved_hits=[hit], generator=FakeGenerator(),
            visual_asset_loader=broken_loader, event_logger=event_logger,
        )

    assert event_logger.events[-1][2]["status"] == "VISUAL_METADATA_FAILED"
    assert not any(event[0] == "generation" for event in event_logger.events)


def test_visual_asset_read_failure_is_recorded_before_generation():
    event_logger = FakeEventLogger()
    element = IndexableElement(
        id=uuid4(), document_id=uuid4(), version_id=uuid4(),
        document_name="規程", heading="表", content="表を参照",
    )
    hit = SearchHit(element=element, score=0.1, rank=1)
    asset = VisualEvidenceAsset(
        element_id=element.id, storage_uri="gs://fixture/page-1.png",
        mime_type="image/png", page_number=1, sha256="unused",
    )

    class BrokenReader:
        def read(self, _asset):
            raise RuntimeError("private asset detail")

    with pytest.raises(RuntimeError):
        generate_simple_qdrant_answer(
            "質問", retrieved_hits=[hit], generator=FakeGenerator(),
            visual_asset_loader=lambda _ids: [asset], asset_reader=BrokenReader(),
            event_logger=event_logger,
        )

    assert event_logger.events[-1][2]["status"] == "VISUAL_ASSET_LOAD_FAILED"
    assert not any(event[0] == "generation" for event in event_logger.events)


def test_visual_asset_bytes_are_reused_for_generation_and_reference():
    element = IndexableElement(
        id=uuid4(), document_id=uuid4(), version_id=uuid4(),
        document_name="通勤手当表", heading="支給額", content="表を参照してください。",
        metadata={"document_key": "DOC-005", "ordinal": 1},
    )
    hit = SearchHit(element=element, score=0.1, rank=1)
    image_bytes = b"reviewed visual fixture"
    asset = VisualEvidenceAsset(
        element_id=element.id,
        storage_uri="gs://fixture/page-1.png",
        mime_type="image/png",
        page_number=1,
        sha256="unused-by-fake-reader",
    )

    class VisualGenerator(FakeGenerator):
        def __init__(self):
            super().__init__()
            self.media = None

        def generate_with_media(self, prompt, *, media):
            self.prompts.append(prompt)
            self.media = media
            return SimpleNamespace(
                text="回答分類: 根拠十分\n\n回答:\n表に基づきます。",
                metadata=lambda: {"model": self.model, "input_tokens": 10},
            )

    class Reader:
        def __init__(self):
            self.read_count = 0

        def read(self, _asset):
            self.read_count += 1
            return image_bytes

    generator = VisualGenerator()
    reader = Reader()
    result = generate_simple_qdrant_answer(
        "支給額を教えてください。",
        retrieved_hits=[hit],
        generator=generator,
        visual_asset_loader=lambda _ids: [asset],
        asset_reader=reader,
        prompt_variant="autoresearch_candidate",
        record_log=False,
    )

    assert reader.read_count == 1
    assert generator.media == [(image_bytes, "image/png")]
    assert result["references"][0]["visual_asset"]["content"] == image_bytes
