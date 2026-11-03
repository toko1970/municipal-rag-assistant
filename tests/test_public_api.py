from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from PIL import Image

from src.api import FeedbackBody, _validate_canonical_origins, create_app
from src.asset_store import VisualEvidenceAsset
from src.public_api_store import KeyRegistration, KeyState, RequestSnapshot
from src.session_security import SessionTokenCodec


CANONICAL_ORIGIN = "https://rag.example.test"
IDEMPOTENCY_KEY = "A" * 43


class FakeStore:
    def __init__(self):
        self.now = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)
        self.session_expires_at = self.now + timedelta(hours=23)
        self.request_id = uuid4()
        self.finished = []
        self.reserved = []
        self.asset = None

    def register_key(self, *, session_hmac, key_hmac, session_expires_at):
        self.session_expires_at = session_expires_at
        return KeyRegistration(
            min(self.now + timedelta(minutes=5), session_expires_at),
            session_expires_at,
        )

    def reserve_question(self, *, session_hmac, key_hmac, body_hash, session_expires_at=None):
        self.reserved.append((session_hmac, key_hmac, body_hash))
        if self.finished:
            return KeyState(
                "COMPLETE",
                self.request_id,
                self.now + timedelta(minutes=5),
                self.session_expires_at,
                self.now,
            )
        return KeyState(
            "IN_PROGRESS",
            None,
            self.now + timedelta(minutes=5),
            self.session_expires_at,
            self.now,
            True,
        )

    def finish_request(self, *, session_hmac, key_hmac, request_id, state):
        self.finished.append((request_id, state))
        return state

    def request_snapshot(self, *, request_id, session_hmac):
        if not self.finished:
            return None
        return RequestSnapshot(
            {
                "request_id": str(self.request_id),
                "answer": "回答本文",
                "answer_label": "根拠十分",
                "answer_status": "SUCCESS",
                "degraded": False,
                "references": [],
                "generation": {"provider": "gemini", "model": "test-model"},
            },
            "SUCCESS",
        )

    def expire_stuck_request(self, *, session_hmac, key_hmac, max_age):
        return KeyState(
            "IN_PROGRESS",
            self.request_id,
            self.now + timedelta(minutes=5),
            self.session_expires_at,
            self.now,
        )

    def authorized_asset(self, *, request_id, reference_id, session_hmac):
        return self.asset


class FakeAssetReader:
    def __init__(self, content):
        self.content = content

    def read(self, asset):
        return asset.verify(self.content)


def _client(*, question_runner=None, readiness_probe=None, canonical_origins=None):
    codec = SessionTokenCodec(
        signing_keys={"key-a": b"a" * 32},
        current_key_id="key-a",
        clock=lambda: 1_800_000_000,
    )
    store = FakeStore()
    app = create_app(
        session_codec=codec,
        store=store,
        question_runner=question_runner
        or (lambda question: {
            "request_id": str(store.request_id),
            "question": question,
            "answer": "回答本文",
            "answer_label": "根拠十分",
            "answer_status": "SUCCESS",
            "degraded": False,
            "references": [],
            "generation": {"provider": "gemini", "model": "test-model"},
        }),
        readiness_probe=readiness_probe or (lambda: None),
        canonical_origin=CANONICAL_ORIGIN if canonical_origins is None else None,
        canonical_origins=canonical_origins,
        frontend_dist=None,
    )
    return TestClient(app, base_url=CANONICAL_ORIGIN), store


def _same_origin_headers():
    return {
        "Origin": CANONICAL_ORIGIN,
        "Sec-Fetch-Site": "same-origin",
        "Idempotency-Key": IDEMPOTENCY_KEY,
    }


def test_root_sets_secure_session_once_without_extending_a_valid_cookie():
    client, _store = _client()

    first = client.get("/")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    cookie = first.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=86400" in cookie

    second = client.get("/")
    assert second.status_code == 200
    assert "set-cookie" not in second.headers


def test_liveness_is_independent_and_readiness_hides_dependency_details():
    client, _store = _client(
        readiness_probe=lambda: (_ for _ in ()).throw(RuntimeError("db-secret-host"))
    )

    live = client.get("/api/health/live")
    ready = client.get("/api/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert "db-secret-host" not in ready.text
    assert ready.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_state_changes_require_exact_origin_and_same_origin_fetch_metadata():
    client, store = _client()
    client.get("/")

    response = client.post(
        "/api/idempotency-keys",
        headers={**_same_origin_headers(), "Origin": "https://attacker.test"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_REJECTED"
    assert store.reserved == []


def test_candidate_and_service_origins_are_explicitly_allowed():
    candidate_origin = "https://review-123-1---rag.example.test"
    client, store = _client(canonical_origins=(CANONICAL_ORIGIN, candidate_origin))
    client.get("/")

    response = client.post(
        "/api/idempotency-keys",
        headers={
            **_same_origin_headers(),
            "Origin": candidate_origin,
        },
    )

    assert response.status_code == 200
    assert len(store.reserved) == 1


@pytest.mark.parametrize(
    "origin",
    ["https://exa mple.com", "https://example.com:443", "https://-bad.example"],
)
def test_canonical_origin_allow_list_rejects_noncanonical_authorities(origin):
    with pytest.raises(ValueError):
        _validate_canonical_origins((origin,))


def test_all_write_routes_require_origin_and_fetch_metadata():
    client, store = _client()
    client.get("/")
    missing_headers = {"Idempotency-Key": IDEMPOTENCY_KEY}

    key = client.post("/api/idempotency-keys", headers=missing_headers)
    question = client.post(
        "/api/requests",
        headers=missing_headers,
        json={"question": "質問"},
    )
    feedback = client.put(
        f"/api/requests/{store.request_id}/feedback",
        headers={},
        json={"value": "採用した", "comment": ""},
    )

    assert [key.status_code, question.status_code, feedback.status_code] == [403, 403, 403]
    assert store.reserved == []


def test_request_boundary_rejects_wrong_content_type_and_oversized_body():
    client, _store = _client()
    client.get("/")
    headers = _same_origin_headers()

    wrong_content_type = client.post(
        "/api/requests",
        headers={**headers, "Content-Type": "text/plain"},
        content='{"question":"質問"}',
    )
    oversized = client.post(
        "/api/requests",
        headers={**headers, "Content-Type": "application/json"},
        content='{"question":"' + ("あ" * 20_000) + '"}',
    )

    assert wrong_content_type.status_code == 415
    assert wrong_content_type.json()["error"]["code"] == "CONTENT_TYPE_UNSUPPORTED"
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "BODY_TOO_LARGE"


def test_openapi_endpoint_serves_the_checked_in_public_contract():
    client, _store = _client()

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["openapi"] == "3.1.0"
    assert "/api/requests/by-idempotency-key" in response.json()["paths"]
    assert "/api/requests/{request_id}/references/{reference_id}/image" in response.json()["paths"]


def test_key_registration_and_question_post_use_existing_rag_result_contract():
    calls = []
    client, store = _client(
        question_runner=lambda question: (
            calls.append(question)
            or {
                "request_id": str(store.request_id),
                "question": question,
                "answer": "回答本文",
                "answer_label": "根拠十分",
                "answer_status": "SUCCESS",
                "degraded": False,
                "references": [],
                "generation": {"provider": "gemini", "model": "test-model"},
            }
        )
    )
    client.get("/")

    issued = client.post("/api/idempotency-keys", headers=_same_origin_headers())
    result = client.post(
        "/api/requests",
        headers=_same_origin_headers(),
        json={"question": "給与支給日はいつですか？"},
    )
    replay = client.post(
        "/api/requests",
        headers=_same_origin_headers(),
        json={"question": "給与支給日はいつですか？"},
    )

    assert issued.status_code == 200
    assert set(issued.json()) == {"submit_by", "session_expires_at"}
    assert result.status_code == 200
    assert result.json()["answer_label"] == "根拠十分"
    assert result.json()["answer_status"] == "SUCCESS"
    assert result.json()["references"] == []
    assert store.finished == [(store.request_id, "COMPLETE")]
    assert replay.status_code == 200
    assert replay.json() == result.json()
    assert calls == ["給与支給日はいつですか？"]


def test_failure_without_an_audited_request_has_stable_same_key_replay():
    class FailureStore(FakeStore):
        def reserve_question(self, *, session_hmac, key_hmac, body_hash, session_expires_at=None):
            self.reserved.append((session_hmac, key_hmac, body_hash))
            state = "IN_PROGRESS" if len(self.reserved) == 1 else "FAILED"
            return KeyState(
                state,
                None,
                self.now + timedelta(minutes=5),
                self.session_expires_at,
                self.now,
                newly_claimed=state == "IN_PROGRESS",
            )

        def request_snapshot(self, *, request_id, session_hmac):
            return None

    store = FailureStore()
    client, _ = _client(question_runner=lambda _question: (_ for _ in ()).throw(TimeoutError()))
    client.app.state.store = store
    client.get("/")
    headers = _same_origin_headers()
    client.post("/api/idempotency-keys", headers=headers)

    first = client.post("/api/requests", headers=headers, json={"question": "質問"})
    replay = client.post("/api/requests", headers=headers, json={"question": "質問"})

    assert first.status_code == replay.status_code == 503
    assert first.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert replay.json() == first.json()


def test_original_post_matches_an_interrupted_state_set_during_provider_work():
    class InterruptedStore(FakeStore):
        interrupted = False

        def reserve_question(self, *, session_hmac, key_hmac, body_hash, session_expires_at=None):
            if self.interrupted:
                return KeyState(
                    "INTERRUPTED",
                    self.request_id,
                    self.now + timedelta(minutes=5),
                    self.session_expires_at,
                    self.now,
                )
            return super().reserve_question(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                body_hash=body_hash,
                session_expires_at=session_expires_at,
            )

        def finish_request(self, *, session_hmac, key_hmac, request_id, state):
            self.finished.append((request_id, "INTERRUPTED"))
            self.interrupted = True
            return "INTERRUPTED"

    store = InterruptedStore()
    client, runner_store = _client()
    store.request_id = runner_store.request_id
    client.app.state.store = store
    client.get("/")
    headers = _same_origin_headers()
    client.post("/api/idempotency-keys", headers=headers)

    response = client.post(
        "/api/requests", headers=headers, json={"question": "質問"}
    )
    replay = client.post(
        "/api/requests", headers=headers, json={"question": "質問"}
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROCESS_INTERRUPTED"
    assert replay.status_code == response.status_code
    assert replay.json() == response.json()
    assert store.finished == [(store.request_id, "INTERRUPTED")]


def test_provider_exception_after_interrupt_returns_the_same_terminal_error():
    class InterruptedStore(FakeStore):
        interrupted = False

        def reserve_question(self, *, session_hmac, key_hmac, body_hash, session_expires_at=None):
            if self.interrupted:
                return KeyState(
                    "INTERRUPTED",
                    self.request_id,
                    self.now + timedelta(minutes=5),
                    self.session_expires_at,
                    self.now,
                )
            return super().reserve_question(
                session_hmac=session_hmac,
                key_hmac=key_hmac,
                body_hash=body_hash,
                session_expires_at=session_expires_at,
            )

        def finish_request(self, *, session_hmac, key_hmac, request_id, state):
            self.finished.append((request_id, "INTERRUPTED"))
            self.interrupted = True
            return "INTERRUPTED"

    store = InterruptedStore()
    client, runner_store = _client(
        question_runner=lambda _question: (_ for _ in ()).throw(TimeoutError())
    )
    store.request_id = runner_store.request_id
    client.app.state.store = store
    client.get("/")
    headers = _same_origin_headers()
    client.post("/api/idempotency-keys", headers=headers)

    first = client.post("/api/requests", headers=headers, json={"question": "質問"})
    replay = client.post("/api/requests", headers=headers, json={"question": "質問"})

    assert first.status_code == replay.status_code == 503
    assert first.json()["error"]["code"] == "PROCESS_INTERRUPTED"
    assert replay.json() == first.json()


def test_snapshot_read_retry_does_not_turn_a_completed_request_into_failure():
    class CompletedStore(FakeStore):
        final_state = None
        snapshot_calls = 0

        def finish_request(self, *, session_hmac, key_hmac, request_id, state):
            if self.final_state is None:
                self.final_state = state
            self.finished.append((request_id, self.final_state))
            return self.final_state

        def request_snapshot(self, *, request_id, session_hmac):
            self.snapshot_calls += 1
            if self.snapshot_calls == 1:
                raise RuntimeError("transient snapshot read failure")
            return super().request_snapshot(
                request_id=request_id, session_hmac=session_hmac
            )

    store = CompletedStore()
    client, runner_store = _client()
    store.request_id = runner_store.request_id
    client.app.state.store = store
    client.get("/")
    headers = _same_origin_headers()
    client.post("/api/idempotency-keys", headers=headers)

    response = client.post(
        "/api/requests", headers=headers, json={"question": "質問"}
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "回答本文"
    assert store.final_state == "COMPLETE"
    assert store.finished == [(store.request_id, "COMPLETE"), (store.request_id, "COMPLETE")]


def test_question_and_feedback_validation_use_unicode_code_points_after_normalization():
    client, _store = _client()
    client.get("/")
    headers = _same_origin_headers()

    too_long = client.post(
        "/api/requests", headers=headers, json={"question": "あ" * 1001}
    )
    empty = client.post("/api/requests", headers=headers, json={"question": " \t "})

    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "QUESTION_TOO_LONG"
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "QUESTION_EMPTY"

    accepted = FeedbackBody(value="採用した", comment="1" * 1998 + "\u0344")
    assert len(accepted.comment) == 2000
    with pytest.raises(ValidationError):
        FeedbackBody(value="採用した", comment="1" * 1999 + "\u0344")
    cleaned = FeedbackBody(value="採用した", comment="a\x00b")
    assert cleaned.comment == "ab"


def test_invalid_feedback_value_uses_the_stable_public_error_code():
    client, store = _client()
    client.get("/")

    response = client.put(
        f"/api/requests/{store.request_id}/feedback",
        headers=_same_origin_headers(),
        json={"value": "unknown", "comment": ""},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FEEDBACK_INVALID"


def test_reference_image_is_private_and_hash_verified():
    image_bytes = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(image_bytes, format="PNG")
    content = image_bytes.getvalue()
    client, store = _client()
    store.asset = VisualEvidenceAsset(
        element_id=uuid4(),
        storage_uri="file:///fixture.png",
        mime_type="image/png",
        page_number=1,
        sha256=sha256(content).hexdigest(),
    )
    client.app.state.asset_reader = FakeAssetReader(content)
    client.get("/")
    request_id = uuid4()

    response = client.get(
        f"/api/requests/{request_id}/references/{store.asset.element_id}/image"
    )

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"

    store.asset = VisualEvidenceAsset(
        element_id=store.asset.element_id,
        storage_uri=store.asset.storage_uri,
        mime_type="image/jpeg",
        page_number=1,
        sha256=store.asset.sha256,
    )
    mismatch = client.get(
        f"/api/requests/{request_id}/references/{store.asset.element_id}/image"
    )
    assert mismatch.status_code == 404
