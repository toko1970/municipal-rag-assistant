"""Composition helpers for local and GCS visual asset adapters."""

from config import (
    GCS_VISUAL_ASSET_BUCKET,
    VISUAL_ASSET_BACKEND,
    VISUAL_ASSET_DIR,
)
from src.asset_store import (
    GCSAssetReader,
    GCSAssetStore,
    LocalAssetReader,
    LocalAssetStore,
)


def get_asset_store():
    if VISUAL_ASSET_BACKEND == "local":
        return LocalAssetStore(VISUAL_ASSET_DIR)
    if VISUAL_ASSET_BACKEND == "gcs":
        return GCSAssetStore(GCS_VISUAL_ASSET_BUCKET)
    raise ValueError(f"未対応のVISUAL_ASSET_BACKENDです: {VISUAL_ASSET_BACKEND}")


def get_asset_reader():
    if VISUAL_ASSET_BACKEND == "local":
        return LocalAssetReader()
    if VISUAL_ASSET_BACKEND == "gcs":
        return GCSAssetReader()
    raise ValueError(f"未対応のVISUAL_ASSET_BACKENDです: {VISUAL_ASSET_BACKEND}")
