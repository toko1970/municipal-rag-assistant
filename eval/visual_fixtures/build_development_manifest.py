"""Build one deterministic manifest from every completed development fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "visual_fixtures"
MANIFEST_PATH = FIXTURE_ROOT / "manifests" / "development_manifest.json"
SCHEMA_PATH = REPOSITORY_ROOT / "design" / "schemas" / "visual-extraction-v1.schema.json"

FIXTURE_SPECS = (
    {
        "fixture_id": "flowchart_dev_001",
        "document_family": "commuting_allowance_application_flow_a",
        "kind": "flowchart",
        "document_path": "eval/visual_fixtures/documents/flowchart_dev_001.pdf",
        "image_path": "eval/visual_fixtures/images/flowchart_dev_001_page_001.png",
        "gold_path": "eval/visual_fixtures/gold/flowchart_dev_001.json",
    },
    {
        "fixture_id": "flowchart_dev_002",
        "document_family": "housing_allowance_eligibility_flow_b",
        "kind": "flowchart",
        "document_path": "eval/visual_fixtures/documents/flowchart_dev_002.pdf",
        "image_path": "eval/visual_fixtures/images/flowchart_dev_002_page_001.png",
        "gold_path": "eval/visual_fixtures/gold/flowchart_dev_002.json",
    },
    {
        "fixture_id": "timeline_dev_001",
        "document_family": "dependent_allowance_deadline_timeline_a",
        "kind": "timeline",
        "document_path": "eval/visual_fixtures/documents/timeline_dev_001.pdf",
        "image_path": "eval/visual_fixtures/images/timeline_dev_001_page_001.png",
        "gold_path": "eval/visual_fixtures/gold/timeline_dev_001.json",
    },
    {
        "fixture_id": "table_dev_001",
        "document_family": "commuting_allowance_amount_table_a",
        "kind": "table",
        "document_path": "eval/visual_fixtures/documents/table_dev_001.pdf",
        "image_path": "eval/visual_fixtures/images/table_dev_001_page_001.png",
        "gold_path": "eval/visual_fixtures/gold/table_dev_001.json",
    },
    {
        "fixture_id": "form_dev_001",
        "document_family": "dependent_allowance_application_form_a",
        "kind": "form",
        "document_path": "eval/visual_fixtures/documents/form_dev_001.pdf",
        "image_path": "eval/visual_fixtures/images/form_dev_001_page_001.png",
        "gold_path": "eval/visual_fixtures/gold/form_dev_001.json",
    },
    {
        "fixture_id": "table_dev_002",
        "document_family": "allowance_revision_comparison_b",
        "kind": "table",
        "document_path": "eval/visual_fixtures/documents/table_dev_002.pdf",
        "image_path": "eval/visual_fixtures/images/table_dev_002_page_001.png",
        "gold_path": "eval/visual_fixtures/gold/table_dev_002.json",
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fixture_entry(spec: dict[str, str]) -> dict[str, Any] | None:
    document_path = REPOSITORY_ROOT / spec["document_path"]
    image_path = REPOSITORY_ROOT / spec["image_path"]
    gold_path = REPOSITORY_ROOT / spec["gold_path"]
    paths = (document_path, image_path, gold_path)
    existing = [path.exists() for path in paths]
    if not any(existing):
        return None
    if not all(existing):
        missing = [str(path.relative_to(REPOSITORY_ROOT)) for path in paths if not path.exists()]
        raise FileNotFoundError(f"fixture artifactが一部不足しています: {missing}")

    with Image.open(image_path) as image:
        width, height = image.size
    return {
        "fixture_id": spec["fixture_id"],
        "document_family": spec["document_family"],
        "kind": spec["kind"],
        "document": {
            "path": spec["document_path"],
            "sha256": sha256(document_path),
        },
        "source_images": [
            {
                "page": 1,
                "path": spec["image_path"],
                "sha256": sha256(image_path),
                "width": width,
                "height": height,
            }
        ],
        "gold": {
            "path": spec["gold_path"],
            "sha256": sha256(gold_path),
        },
    }


def write_development_manifest() -> None:
    fixtures = [entry for spec in FIXTURE_SPECS if (entry := fixture_entry(spec)) is not None]
    if not fixtures:
        raise ValueError("development fixtureがありません")
    manifest = {
        "manifest_version": "1.0",
        "split": "development",
        "paths_relative_to": "repository_root",
        "generated_by": "eval/visual_fixtures/build_development_manifest.py",
        "schema": {
            "path": "design/schemas/visual-extraction-v1.schema.json",
            "sha256": sha256(SCHEMA_PATH),
        },
        "fixtures": fixtures,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_development_manifest()
    print(MANIFEST_PATH.relative_to(REPOSITORY_ROOT))
