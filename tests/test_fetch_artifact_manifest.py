"""Artifact Registry manifest snapshots are pinned and byte-verified."""

import hashlib
import json

import pytest

from scripts.fetch_artifact_manifest import (
    IMAGE_REPOSITORY,
    ManifestFetchError,
    validate_manifest_body,
)


def _body():
    return json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [],
        },
        separators=(",", ":"),
    ).encode()


def test_manifest_body_must_match_the_pinned_artifact_digest():
    body = _body()
    image = f"{IMAGE_REPOSITORY}@sha256:{hashlib.sha256(body).hexdigest()}"

    assert validate_manifest_body(image, body)["manifests"] == []

    with pytest.raises(ManifestFetchError, match="digest"):
        validate_manifest_body(image, body + b" ")


def test_manifest_fetch_rejects_unpinned_or_unapproved_image_references():
    body = _body()
    digest = hashlib.sha256(body).hexdigest()

    with pytest.raises(ManifestFetchError, match="pinned application image"):
        validate_manifest_body(f"other.example/image@sha256:{digest}", body)
    with pytest.raises(ManifestFetchError, match="pinned application image"):
        validate_manifest_body(f"{IMAGE_REPOSITORY}:latest", body)
