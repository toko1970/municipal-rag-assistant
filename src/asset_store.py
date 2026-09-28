"""Binary asset storage boundary for page images used as visual evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse
from uuid import UUID

from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage


@dataclass(frozen=True)
class StoredAsset:
    key: str
    storage_uri: str
    mime_type: str
    sha256: str


@dataclass(frozen=True)
class VisualEvidenceAsset:
    """Metadata needed to verify and use one stored visual evidence image."""

    element_id: UUID
    storage_uri: str
    mime_type: str
    page_number: int
    sha256: str
    bbox: dict[str, float] | None = None

    def verify(self, content: bytes) -> bytes:
        actual = hashlib.sha256(content).hexdigest()
        if actual != self.sha256:
            raise ValueError(
                f"visual assetのSHA-256が一致しません: element_id={self.element_id}"
            )
        return content


class AssetReader(Protocol):
    def read(self, asset: VisualEvidenceAsset) -> bytes: ...


class AssetStore(Protocol):
    def put_page_image(
        self, *, document_key: str, page_number: int, content: bytes
    ) -> StoredAsset: ...


class LocalAssetStore:
    """Store immutable page images below one configured local directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put_page_image(
        self, *, document_key: str, page_number: int, content: bytes
    ) -> StoredAsset:
        if not document_key or any(part in document_key for part in ("/", "\\", "..")):
            raise ValueError("document_keyにはpath区切りや..を使用できません")
        if page_number < 1:
            raise ValueError("page_numberは1以上である必要があります")
        digest = hashlib.sha256(content).hexdigest()
        key = f"{document_key}/page-{page_number:04d}-{digest[:16]}.png"
        path = (self.root / key).resolve()
        path.relative_to(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != content:
            raise RuntimeError("同じasset keyへ異なる内容を書き込めません")
        if not path.exists():
            path.write_bytes(content)
        return StoredAsset(
            key=key,
            storage_uri=path.as_uri(),
            mime_type="image/png",
            sha256=digest,
        )


class LocalAssetReader:
    def read(self, asset: VisualEvidenceAsset) -> bytes:
        parsed = urlparse(asset.storage_uri)
        if parsed.scheme not in {"", "file"}:
            raise ValueError(
                f"LocalAssetReaderは未対応のURIです: {asset.storage_uri}"
            )
        path = (
            Path(unquote(parsed.path)) if parsed.scheme == "file" else Path(parsed.path)
        )
        return asset.verify(path.read_bytes())


class GCSAssetStore:
    """Store immutable page images in one preconfigured private GCS bucket."""

    def __init__(self, bucket_name: str, client=None) -> None:
        if not bucket_name:
            raise ValueError("GCS bucket nameが設定されていません")
        self.bucket_name = bucket_name
        self.client = client or storage.Client()

    def put_page_image(
        self, *, document_key: str, page_number: int, content: bytes
    ) -> StoredAsset:
        if not document_key or any(
            part in document_key for part in ("/", "\\", "..")
        ):
            raise ValueError("document_keyにはpath区切りや..を使用できません")
        if page_number < 1:
            raise ValueError("page_numberは1以上である必要があります")
        digest = hashlib.sha256(content).hexdigest()
        key = f"{document_key}/page-{page_number:04d}-{digest[:16]}.png"
        blob = self.client.bucket(self.bucket_name).blob(key)
        blob.metadata = {"sha256": digest}
        try:
            blob.upload_from_string(
                content,
                content_type="image/png",
                if_generation_match=0,
                retry=None,
            )
        except PreconditionFailed:
            existing = blob.download_as_bytes(retry=None)
            if hashlib.sha256(existing).hexdigest() != digest:
                raise RuntimeError(
                    "同じGCS object keyへ異なる内容が保存されています"
                ) from None
        return StoredAsset(
            key=key,
            storage_uri=f"gs://{self.bucket_name}/{key}",
            mime_type="image/png",
            sha256=digest,
        )


class GCSAssetReader:
    def __init__(self, client=None) -> None:
        self.client = client or storage.Client()

    def read(self, asset: VisualEvidenceAsset) -> bytes:
        parsed = urlparse(asset.storage_uri)
        if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.lstrip("/"):
            raise ValueError(f"GCS URIが不正です: {asset.storage_uri}")
        blob = self.client.bucket(parsed.netloc).blob(parsed.path.lstrip("/"))
        return asset.verify(blob.download_as_bytes(retry=None))
