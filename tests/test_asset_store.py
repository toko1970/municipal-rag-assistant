import hashlib
from uuid import uuid4

import pytest
from google.api_core.exceptions import PreconditionFailed

from src.asset_store import (
    GCSAssetReader,
    GCSAssetStore,
    LocalAssetReader,
    LocalAssetStore,
    VisualEvidenceAsset,
)


class FakeBlob:
    def __init__(self, content=None):
        self.content = content
        self.metadata = None
        self.upload_kwargs = None

    def upload_from_string(self, content, **kwargs):
        self.upload_kwargs = kwargs
        if self.content is not None:
            raise PreconditionFailed("already exists")
        self.content = content

    def download_as_bytes(self, **_kwargs):
        return self.content


class FakeBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, key):
        return self.blobs.setdefault(key, FakeBlob())


class FakeClient:
    def __init__(self):
        self.buckets = {}

    def bucket(self, name):
        return self.buckets.setdefault(name, FakeBucket())


def test_local_store_and_reader_use_file_uri_and_verify_hash(tmp_path) -> None:
    stored = LocalAssetStore(tmp_path).put_page_image(
        document_key="DOC-1", page_number=1, content=b"png"
    )
    asset = VisualEvidenceAsset(
        element_id=uuid4(),
        storage_uri=stored.storage_uri,
        mime_type=stored.mime_type,
        page_number=1,
        sha256=stored.sha256,
    )

    assert stored.storage_uri.startswith("file://")
    assert LocalAssetReader().read(asset) == b"png"


def test_gcs_store_uses_create_only_precondition_and_returns_uri() -> None:
    client = FakeClient()
    stored = GCSAssetStore("private-bucket", client=client).put_page_image(
        document_key="DOC-1", page_number=2, content=b"png"
    )
    blob = client.bucket("private-bucket").blob(stored.key)

    assert stored.storage_uri == f"gs://private-bucket/{stored.key}"
    assert blob.upload_kwargs["if_generation_match"] == 0
    assert blob.upload_kwargs["retry"] is None
    assert blob.metadata == {"sha256": hashlib.sha256(b"png").hexdigest()}


def test_gcs_store_accepts_idempotent_duplicate_and_rejects_different_object() -> None:
    client = FakeClient()
    store = GCSAssetStore("private-bucket", client=client)
    first = store.put_page_image(document_key="DOC-1", page_number=1, content=b"png")
    second = store.put_page_image(document_key="DOC-1", page_number=1, content=b"png")
    assert first == second

    blob = client.bucket("private-bucket").blob(first.key)
    blob.content = b"changed"
    with pytest.raises(RuntimeError, match="異なる内容"):
        store.put_page_image(document_key="DOC-1", page_number=1, content=b"png")


def test_gcs_reader_downloads_named_object_and_verifies_hash() -> None:
    client = FakeClient()
    blob = client.bucket("private-bucket").blob("DOC-1/page.png")
    blob.content = b"png"
    asset = VisualEvidenceAsset(
        element_id=uuid4(),
        storage_uri="gs://private-bucket/DOC-1/page.png",
        mime_type="image/png",
        page_number=1,
        sha256=hashlib.sha256(b"png").hexdigest(),
    )

    assert GCSAssetReader(client).read(asset) == b"png"
    assert blob.download_as_bytes(retry=None) == b"png"


def test_reader_rejects_hash_mismatch() -> None:
    client = FakeClient()
    client.bucket("private-bucket").blob("page.png").content = b"changed"
    asset = VisualEvidenceAsset(
        element_id=uuid4(),
        storage_uri="gs://private-bucket/page.png",
        mime_type="image/png",
        page_number=1,
        sha256="0" * 64,
    )

    with pytest.raises(ValueError, match="SHA-256"):
        GCSAssetReader(client).read(asset)
