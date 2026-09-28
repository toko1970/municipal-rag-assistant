"""Binary asset storage boundary for page images used as visual evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredAsset:
    key: str
    local_path: str
    mime_type: str
    sha256: str


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
            local_path=str(path),
            mime_type="image/png",
            sha256=digest,
        )
