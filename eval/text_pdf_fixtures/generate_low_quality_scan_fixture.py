"""Generate one deterministic low-contrast image-only PDF fixture."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from eval.validate_visual_fixture import load_json
from eval.visual_fixtures.generate_flowchart_fixture import sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "text_pdf_fixtures"
CLEAN_SOURCE_PATH = FIXTURE_ROOT / "images" / "scan_text_dev_001_source.png"
CLEAN_GOLD_PATH = FIXTURE_ROOT / "gold" / "scan_text_dev_001.json"
PDF_PATH = FIXTURE_ROOT / "documents" / "low_quality_scan_dev_001.pdf"
SOURCE_IMAGE_PATH = FIXTURE_ROOT / "images" / "low_quality_scan_dev_001_source.png"
RENDERED_IMAGE_PATH = (
    FIXTURE_ROOT / "images" / "low_quality_scan_dev_001_page_001.png"
)
GOLD_PATH = FIXTURE_ROOT / "gold" / "low_quality_scan_dev_001.json"
MANIFEST_PATH = (
    FIXTURE_ROOT / "manifests" / "low_quality_development_manifest.json"
)
SCHEMA_PATH = REPOSITORY_ROOT / "design" / "schemas" / "low-quality-scan-v1.schema.json"
PAGE_WIDTH, PAGE_HEIGHT = A4
SOURCE_DPI = 300
WHITE_BLEND_ALPHA = 0.75
FIXTURE_DYNAMIC_RANGE_MAX = 60


def grayscale_dynamic_range(image: Image.Image) -> int:
    minimum, maximum = image.convert("L").getextrema()
    return maximum - minimum


def create_low_contrast_image() -> int:
    SOURCE_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(CLEAN_SOURCE_PATH) as clean:
        clean_rgb = clean.convert("RGB")
        white = Image.new("RGB", clean_rgb.size, "white")
        degraded = Image.blend(clean_rgb, white, WHITE_BLEND_ALPHA)
    dynamic_range = grayscale_dynamic_range(degraded)
    if dynamic_range > FIXTURE_DYNAMIC_RANGE_MAX:
        raise ValueError("生成画像がfixtureのlow contrast条件を満たしません")
    degraded.save(
        SOURCE_IMAGE_PATH,
        format="PNG",
        compress_level=9,
        dpi=(SOURCE_DPI, SOURCE_DPI),
    )
    return dynamic_range


def create_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(
        str(PDF_PATH),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle("時間外勤務手当 申請時の確認事項（架空・低コントラスト）")
    pdf.setAuthor("RAG Portfolio Fixture Generator")
    pdf.drawImage(
        ImageReader(str(SOURCE_IMAGE_PATH)),
        0,
        0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        preserveAspectRatio=False,
        mask=None,
    )
    pdf.showPage()
    pdf.save()


def render_page_image() -> None:
    RENDERED_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    subprocess.run(
        [
            renderer,
            "-singlefile",
            "-png",
            "-r",
            "150",
            str(PDF_PATH),
            str(RENDERED_IMAGE_PATH.with_suffix("")),
        ],
        check=True,
    )


def write_gold(dynamic_range: int) -> None:
    clean_gold = load_json(CLEAN_GOLD_PATH)
    clean_page = clean_gold["pages"][0]
    gold = {
        "schema_version": "1.0",
        "kind": "low_quality_scanned_text",
        "title": "時間外勤務手当 申請時の確認事項（架空・低コントラスト）",
        "page_count": 1,
        "expected_full_text": clean_gold["expected_full_text"],
        "critical_values": clean_gold["critical_values"],
        "input_characteristics": {
            "text_layer_expected": False,
            "dpi": SOURCE_DPI,
            "rotation_degrees": 0,
            "quality": "low_quality",
        },
        "quality_assessment": {
            "degradation": "low_contrast",
            "measurement": {
                "metric": "grayscale_dynamic_range",
                "value": dynamic_range,
                "fixture_gate_max": FIXTURE_DYNAMIC_RANGE_MAX,
            },
        },
        "expected_gate": {
            "extraction_result": "REVIEW_REQUIRED",
            "document_status": "WAITING_REVIEW",
            "review_reasons": ["LOW_CONTRAST"],
            "automatic_ready_allowed": False,
        },
        "confidence": {
            "source": "unavailable",
            "value": None,
            "review_required": True,
        },
        "pages": [
            {
                "page": 1,
                "width_points": round(PAGE_WIDTH, 4),
                "height_points": round(PAGE_HEIGHT, 4),
                "source_image_sha256": sha256(SOURCE_IMAGE_PATH),
                "expected_text": clean_page["expected_text"],
                "regions": deepcopy(clean_page["regions"]),
            }
        ],
    }
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLD_PATH.write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_manifest() -> None:
    with Image.open(CLEAN_SOURCE_PATH) as clean_image:
        clean_range = grayscale_dynamic_range(clean_image)
    with Image.open(SOURCE_IMAGE_PATH) as source_image:
        source_size = source_image.size
        source_dpi = round(source_image.info["dpi"][0])
    manifest = {
        "manifest_version": "1.0",
        "split": "development",
        "paths_relative_to": "repository_root",
        "generated_by": "eval/text_pdf_fixtures/generate_low_quality_scan_fixture.py",
        "schema": {
            "path": "design/schemas/low-quality-scan-v1.schema.json",
            "sha256": sha256(SCHEMA_PATH),
        },
        "clean_reference": {
            "source_image": {
                "path": "eval/text_pdf_fixtures/images/scan_text_dev_001_source.png",
                "sha256": sha256(CLEAN_SOURCE_PATH),
                "grayscale_dynamic_range": clean_range,
            },
            "gold": {
                "path": "eval/text_pdf_fixtures/gold/scan_text_dev_001.json",
                "sha256": sha256(CLEAN_GOLD_PATH),
            },
        },
        "fixtures": [
            {
                "fixture_id": "low_quality_scan_dev_001",
                "document_family": "overtime_allowance_confirmation_low_contrast_a",
                "kind": "low_quality_scanned_text",
                "document": {
                    "path": "eval/text_pdf_fixtures/documents/low_quality_scan_dev_001.pdf",
                    "sha256": sha256(PDF_PATH),
                },
                "source_image": {
                    "path": (
                        "eval/text_pdf_fixtures/images/"
                        "low_quality_scan_dev_001_source.png"
                    ),
                    "sha256": sha256(SOURCE_IMAGE_PATH),
                    "width": source_size[0],
                    "height": source_size[1],
                    "dpi": source_dpi,
                },
                "rendered_page": {
                    "path": (
                        "eval/text_pdf_fixtures/images/"
                        "low_quality_scan_dev_001_page_001.png"
                    ),
                    "sha256": sha256(RENDERED_IMAGE_PATH),
                },
                "gold": {
                    "path": "eval/text_pdf_fixtures/gold/low_quality_scan_dev_001.json",
                    "sha256": sha256(GOLD_PATH),
                },
            }
        ],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    dynamic_range = create_low_contrast_image()
    create_pdf()
    render_page_image()
    write_gold(dynamic_range)
    write_manifest()
    for path in (
        PDF_PATH,
        SOURCE_IMAGE_PATH,
        RENDERED_IMAGE_PATH,
        GOLD_PATH,
        MANIFEST_PATH,
    ):
        print(path.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
