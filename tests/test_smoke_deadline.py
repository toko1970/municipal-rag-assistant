import hashlib
from unittest.mock import patch
from uuid import uuid4

import pytest

from scripts import manage_rag_v2
from src import embeddings
from src.asset_store import GCSAssetReader, VisualEvidenceAsset
from src.llm_provider import GeminiProvider
from src.qdrant_index import QdrantVectorIndex
from src.smoke_context import SmokeDeadline, bind_smoke_context


def test_smoke_stops_hung_invocation_at_its_deadline_and_emits_safe_progress():
    now = [0.0]
    events = []

    def blocked(_question):
        now[0] = 91.0
        SmokeDeadline.current().remaining_seconds()

    with patch.object(manage_rag_v2, "generate_qdrant_answer", side_effect=blocked):
        report = manage_rag_v2.smoke(
            case_ids=["salary_day", "missing_document"],
            max_cases=2,
            max_attempts=2,
            max_runtime_seconds=720,
            max_invocation_seconds=90,
            clock=lambda: now[0],
            progress=events.append,
        )

    assert report["structural_passed"] is False
    assert report["results"][0]["failure_kind"] == "TIMEOUT"
    assert report["not_run_case_ids"] == ["missing_document"]
    assert events
    assert all(
        set(event)
        <= {
            "event",
            "case_id",
            "stage",
            "attempt",
            "elapsed_ms",
            "status",
            "request_id",
        }
        for event in events
    )
    assert "question" not in str(events) and "answer" not in str(events)
    assert any(
        event["stage"] == "RAG_QUERY" and event["status"] == "timed_out"
        for event in events
    )


def test_smoke_backoff_sleep_is_capped_by_overall_deadline():
    now = [0.0]
    events = []

    def unavailable(_question):
        now[0] += 2.5
        raise RuntimeError("503 UNAVAILABLE")

    def fake_sleep(seconds):
        now[0] += seconds

    with patch.object(
        manage_rag_v2, "generate_qdrant_answer", side_effect=unavailable
    ) as generate:
        report = manage_rag_v2.smoke(
            case_ids=["salary_day"],
            max_cases=1,
            max_attempts=2,
            max_503_retries=1,
            max_runtime_seconds=6,
            max_invocation_seconds=90,
            clock=lambda: now[0],
            sleep=fake_sleep,
            progress=events.append,
        )

    generate.assert_called_once()
    assert report["elapsed_ms"] == 6000
    assert report["results"][0]["failure_kind"] == "TIMEOUT"
    assert any(event["status"] == "timed_out" for event in events)


def test_smoke_deadline_is_passed_to_embedding_and_gemini_clients():
    now = [10.0]
    deadline = SmokeDeadline(100.0, lambda: now[0])
    with bind_smoke_context(deadline):
        with patch.object(embeddings, "GOOGLE_API_KEY", "test-key"):
            actual_embeddings = embeddings.get_embeddings()
        assert actual_embeddings.client._api_client._http_options.client_args == {
            "timeout": 90.0
        }
        with (
            patch.object(embeddings, "GOOGLE_API_KEY", "test-key"),
            patch.object(embeddings, "GoogleGenerativeAIEmbeddings") as make_embeddings,
        ):
            embeddings.get_embeddings()
        make_embeddings.assert_called_once_with(
            model=embeddings.EMBEDDING_MODEL_NAME,
            google_api_key="test-key",
            client_args={"timeout": 90.0},
        )

        with patch("src.llm_provider.ChatGoogleGenerativeAI") as make_chat:
            GeminiProvider("gemini-test", api_key="test-key", request_timeout=45.0)
        assert make_chat.call_args.kwargs["request_timeout"] == 45.0


def test_network_adapters_keep_existing_arguments_without_smoke_context():
    with (
        patch.object(embeddings, "GOOGLE_API_KEY", "test-key"),
        patch.object(embeddings, "GoogleGenerativeAIEmbeddings") as make_embeddings,
    ):
        embeddings.get_embeddings()
    assert make_embeddings.call_args.kwargs == {
        "model": embeddings.EMBEDDING_MODEL_NAME,
        "google_api_key": "test-key",
    }


def test_smoke_deadline_reaches_qdrant_and_gcs_network_operations():
    now = [15.0]
    calls = {}

    class Qdrant:
        def query_points(self, **kwargs):
            calls["qdrant"] = kwargs
            return type("Response", (), {"points": []})()

    class Blob:
        def download_as_bytes(self, **kwargs):
            calls["gcs"] = kwargs
            return b"png"

    class Bucket:
        def blob(self, _key):
            return Blob()

    class Storage:
        def bucket(self, _name):
            return Bucket()

    asset = VisualEvidenceAsset(
        element_id=uuid4(),
        storage_uri="gs://bucket/doc/page.png",
        mime_type="image/png",
        page_number=1,
        sha256=hashlib.sha256(b"png").hexdigest(),
    )
    with bind_smoke_context(SmokeDeadline(100, lambda: now[0])):
        QdrantVectorIndex(client=Qdrant()).search([0.1], 1)
        assert GCSAssetReader(client=Storage()).read(asset) == b"png"
    assert calls["qdrant"]["timeout"] == 85
    assert calls["gcs"]["timeout"] == 85.0


def test_smoke_deadline_validation_rejects_bounds_larger_than_plan():
    with patch.object(manage_rag_v2, "generate_qdrant_answer") as generate:
        with pytest.raises(ValueError):
            manage_rag_v2.smoke(max_runtime_seconds=721)
        with pytest.raises(ValueError):
            manage_rag_v2.smoke(max_invocation_seconds=91)
    generate.assert_not_called()
