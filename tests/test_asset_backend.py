from unittest.mock import patch

import pytest

import src.asset_backend as backend
from src.asset_store import GCSAssetReader, LocalAssetReader, LocalAssetStore


def test_local_backend_uses_configured_directory(tmp_path) -> None:
    with (
        patch.object(backend, "VISUAL_ASSET_BACKEND", "local"),
        patch.object(backend, "VISUAL_ASSET_DIR", tmp_path),
    ):
        store = backend.get_asset_store()
        reader = backend.get_asset_reader()

    assert isinstance(store, LocalAssetStore)
    assert store.root == tmp_path.resolve()
    assert isinstance(reader, LocalAssetReader)


def test_gcs_backend_requires_bucket_name() -> None:
    with (
        patch.object(backend, "VISUAL_ASSET_BACKEND", "gcs"),
        patch.object(backend, "GCS_VISUAL_ASSET_BUCKET", ""),
        pytest.raises(ValueError, match="bucket"),
    ):
        backend.get_asset_store()


def test_gcs_reader_is_selected_without_eager_network_call() -> None:
    fake_client = object()
    with (
        patch.object(backend, "VISUAL_ASSET_BACKEND", "gcs"),
        patch("src.asset_backend.GCSAssetReader", return_value=GCSAssetReader(fake_client)),
    ):
        reader = backend.get_asset_reader()

    assert isinstance(reader, GCSAssetReader)
    assert reader.client is fake_client
