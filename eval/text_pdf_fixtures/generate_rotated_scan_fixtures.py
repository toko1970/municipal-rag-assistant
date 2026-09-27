"""Generate deterministic 90/180/270-degree PDF rotation fixtures."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image
import pymupdf

from eval.validate_visual_fixture import load_json
from eval.visual_fixtures.generate_flowchart_fixture import sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "text_pdf_fixtures"
SOURCE_PDF_PATH = FIXTURE_ROOT / "documents" / "scan_text_dev_001.pdf"
SOURCE_IMAGE_PATH = FIXTURE_ROOT / "images" / "scan_text_dev_001_source.png"
SOURCE_GOLD_PATH = FIXTURE_ROOT / "gold" / "scan_text_dev_001.json"
UPRIGHT_REFERENCE_PATH = (
    FIXTURE_ROOT / "images" / "scan_text_dev_001_page_001.png"
)
MANIFEST_PATH = FIXTURE_ROOT / "manifests" / "rotation_development_manifest.json"
SCHEMA_PATH = (
    REPOSITORY_ROOT / "design" / "schemas" / "rotated-scan-extraction-v1.schema.json"
)
ANGLES = (90, 180, 270)


def artifact_paths(angle: int) -> dict[str, Path]:
    stem = f"rotated_scan_dev_{angle:03d}"
    return {
        "document": FIXTURE_ROOT / "documents" / f"{stem}.pdf",
        "raw_image": FIXTURE_ROOT / "images" / f"{stem}_page_001.png",
        "normalized_image": (
            FIXTURE_ROOT / "images" / f"{stem}_normalized_page_001.png"
        ),
        "gold": FIXTURE_ROOT / "gold" / f"{stem}.json",
    }


def render_pdf(pdf_path: Path, image_path: Path) -> None:
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            renderer,
            "-singlefile",
            "-png",
            "-r",
            "150",
            str(pdf_path),
            str(image_path.with_suffix("")),
        ],
        check=True,
    )


def create_rotated_pdf(angle: int, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(SOURCE_PDF_PATH) as document:
        document[0].set_rotation(angle)
        document.save(
            output_path,
            garbage=4,
            deflate=True,
            no_new_id=True,
            reproducible=True,
        )


def render_normalized_pdf(rotated_path: Path, image_path: Path) -> None:
    with tempfile.TemporaryDirectory() as directory:
        normalized_pdf = Path(directory) / "normalized.pdf"
        with pymupdf.open(rotated_path) as document:
            document[0].set_rotation(0)
            document.save(
                normalized_pdf,
                garbage=4,
                deflate=True,
                no_new_id=True,
                reproducible=True,
            )
        render_pdf(normalized_pdf, image_path)


def write_gold(angle: int, paths: dict[str, Path]) -> None:
    source_gold = load_json(SOURCE_GOLD_PATH)
    source_page = source_gold["pages"][0]
    with pymupdf.open(paths["document"]) as document:
        page = document[0]
        media_width = round(page.mediabox.width, 4)
        media_height = round(page.mediabox.height, 4)
        displayed_width = round(page.rect.width, 4)
        displayed_height = round(page.rect.height, 4)

    gold = {
        "schema_version": "1.0",
        "kind": "rotated_scanned_text",
        "title": f"時間外勤務手当 申請時の確認事項（架空・{angle}度回転）",
        "page_count": 1,
        "expected_full_text": source_gold["expected_full_text"],
        "critical_values": source_gold["critical_values"],
        "input_characteristics": {
            "text_layer_expected": False,
            "dpi": source_gold["input_characteristics"]["dpi"],
            "rotation_degrees": angle,
            "quality": "clean",
        },
        "normalization": {
            "target_rotation_degrees": 0,
            "coordinate_space": "upright_source",
        },
        "confidence": {
            "source": "unavailable",
            "value": None,
            "review_required": True,
        },
        "pages": [
            {
                "page": 1,
                "media_width_points": media_width,
                "media_height_points": media_height,
                "displayed_width_points": displayed_width,
                "displayed_height_points": displayed_height,
                "source_image_sha256": sha256(SOURCE_IMAGE_PATH),
                "expected_normalized_image_sha256": sha256(
                    UPRIGHT_REFERENCE_PATH
                ),
                "expected_text": source_page["expected_text"],
                "regions": deepcopy(source_page["regions"]),
            }
        ],
    }
    paths["gold"].parent.mkdir(parents=True, exist_ok=True)
    paths["gold"].write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fixture_entry(angle: int, paths: dict[str, Path]) -> dict[str, object]:
    stem = f"rotated_scan_dev_{angle:03d}"
    with Image.open(paths["raw_image"]) as raw_image:
        raw_size = raw_image.size
    with Image.open(paths["normalized_image"]) as normalized_image:
        normalized_size = normalized_image.size
    return {
        "fixture_id": stem,
        "document_family": "overtime_allowance_confirmation_rotation_a",
        "kind": "rotated_scanned_text",
        "rotation_degrees": angle,
        "document": {
            "path": f"eval/text_pdf_fixtures/documents/{stem}.pdf",
            "sha256": sha256(paths["document"]),
        },
        "raw_rendered_page": {
            "path": f"eval/text_pdf_fixtures/images/{stem}_page_001.png",
            "sha256": sha256(paths["raw_image"]),
            "width": raw_size[0],
            "height": raw_size[1],
        },
        "normalized_page": {
            "path": (
                f"eval/text_pdf_fixtures/images/{stem}_normalized_page_001.png"
            ),
            "sha256": sha256(paths["normalized_image"]),
            "width": normalized_size[0],
            "height": normalized_size[1],
        },
        "gold": {
            "path": f"eval/text_pdf_fixtures/gold/{stem}.json",
            "sha256": sha256(paths["gold"]),
        },
    }


def write_manifest(entries: list[dict[str, object]]) -> None:
    with Image.open(SOURCE_IMAGE_PATH) as source_image:
        source_size = source_image.size
        source_dpi = source_image.info["dpi"]
    manifest = {
        "manifest_version": "1.0",
        "split": "development",
        "paths_relative_to": "repository_root",
        "generated_by": "eval/text_pdf_fixtures/generate_rotated_scan_fixtures.py",
        "schema": {
            "path": "design/schemas/rotated-scan-extraction-v1.schema.json",
            "sha256": sha256(SCHEMA_PATH),
        },
        "source_fixture": {
            "fixture_id": "scan_text_dev_001",
            "source_image": {
                "path": "eval/text_pdf_fixtures/images/scan_text_dev_001_source.png",
                "sha256": sha256(SOURCE_IMAGE_PATH),
                "width": source_size[0],
                "height": source_size[1],
                "dpi": round(source_dpi[0]),
            },
            "upright_reference_page": {
                "path": (
                    "eval/text_pdf_fixtures/images/scan_text_dev_001_page_001.png"
                ),
                "sha256": sha256(UPRIGHT_REFERENCE_PATH),
            },
            "gold": {
                "path": "eval/text_pdf_fixtures/gold/scan_text_dev_001.json",
                "sha256": sha256(SOURCE_GOLD_PATH),
            },
        },
        "fixtures": entries,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    entries = []
    for angle in ANGLES:
        paths = artifact_paths(angle)
        create_rotated_pdf(angle, paths["document"])
        render_pdf(paths["document"], paths["raw_image"])
        render_normalized_pdf(paths["document"], paths["normalized_image"])
        write_gold(angle, paths)
        entries.append(fixture_entry(angle, paths))
    write_manifest(entries)
    for angle in ANGLES:
        for path in artifact_paths(angle).values():
            print(path.relative_to(REPOSITORY_ROOT))
    print(MANIFEST_PATH.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
