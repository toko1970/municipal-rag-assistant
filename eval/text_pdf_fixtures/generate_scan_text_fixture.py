"""Generate one deterministic image-only Japanese PDF fixture and its gold."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from eval.visual_fixtures.generate_flowchart_fixture import find_japanese_font, sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "text_pdf_fixtures"
PDF_PATH = FIXTURE_ROOT / "documents" / "scan_text_dev_001.pdf"
SOURCE_IMAGE_PATH = FIXTURE_ROOT / "images" / "scan_text_dev_001_source.png"
RENDERED_IMAGE_PATH = (
    FIXTURE_ROOT / "images" / "scan_text_dev_001_page_001.png"
)
GOLD_PATH = FIXTURE_ROOT / "gold" / "scan_text_dev_001.json"
MANIFEST_PATH = FIXTURE_ROOT / "manifests" / "scan_development_manifest.json"
SCHEMA_PATH = (
    REPOSITORY_ROOT / "design" / "schemas" / "scan-text-extraction-v1.schema.json"
)

PAGE_WIDTH_POINTS, PAGE_HEIGHT_POINTS = A4
SOURCE_DPI = 300
SOURCE_WIDTH = 2480
SOURCE_HEIGHT = 3508

TEXT_BLOCKS = (
    ("title", "時間外勤務手当 申請時の確認事項（架空）", 225, 170, 72, "#FFFFFF"),
    (
        "document_meta",
        "文書番号: 架空人給第24号　施行日: 2026年6月1日",
        225,
        365,
        34,
        "#DDEAF4",
    ),
    ("purpose_heading", "1. 対象", 225, 650, 48, "#174A6E"),
    (
        "purpose",
        "所属長の命令により正規の勤務時間を超えて勤務した職員を対象とする。",
        225,
        750,
        38,
        "#172033",
    ),
    ("deadline_heading", "2. 提出期限", 225, 980, 48, "#174A6E"),
    (
        "deadline",
        "給与事務担当者は、勤務した月の翌月10日までに申請内容を確認する。",
        225,
        1080,
        38,
        "#172033",
    ),
    ("attachments_heading", "3. 確認書類", 225, 1310, 48, "#174A6E"),
    ("attachment_1", "・時間外勤務命令簿", 285, 1415, 38, "#172033"),
    ("attachment_2", "・勤務実績一覧", 285, 1505, 38, "#172033"),
    ("amount_heading", "4. 支給額の確認", 225, 1740, 48, "#174A6E"),
    (
        "amount",
        "申請額が30,000円以上の場合は、所属長確認書を添付する。",
        225,
        1840,
        38,
        "#172033",
    ),
    ("processing_heading", "5. 処理期限", 225, 2070, 48, "#174A6E"),
    (
        "processing",
        "人事給与課は受付後5営業日以内に確認結果を所属へ通知する。",
        225,
        2170,
        38,
        "#172033",
    ),
    (
        "note",
        "注: 本文書はRAG評価専用の架空資料であり、実在の制度ではない。",
        225,
        3180,
        30,
        "#526579",
    ),
)


def expected_text() -> str:
    return "\n".join(block[1] for block in TEXT_BLOCKS)


def normalized_bbox(box: tuple[int, int, int, int]) -> dict[str, float]:
    x0, y0, x1, y1 = box
    return {
        "x0": round(x0 / SOURCE_WIDTH, 4),
        "y0": round(y0 / SOURCE_HEIGHT, 4),
        "x1": round(x1 / SOURCE_WIDTH, 4),
        "y1": round(y1 / SOURCE_HEIGHT, 4),
    }


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(find_japanese_font()), size, index=0)


def create_source_image() -> list[dict[str, object]]:
    SOURCE_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (SOURCE_WIDTH, SOURCE_HEIGHT), "#F7F9FC")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, SOURCE_WIDTH, 500), fill="#243B53")
    draw.line((225, 575, SOURCE_WIDTH - 225, 575), fill="#B8CBD9", width=4)

    regions = []
    for block_id, text, x, y, size, color in TEXT_BLOCKS:
        font = load_font(size)
        draw.text((x, y), text, font=font, fill=color)
        box = draw.textbbox((x, y), text, font=font)
        regions.append(
            {"id": block_id, "text": text, "bbox": normalized_bbox(box)}
        )

    image.save(
        SOURCE_IMAGE_PATH,
        format="PNG",
        compress_level=9,
        dpi=(SOURCE_DPI, SOURCE_DPI),
    )
    return regions


def create_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(
        str(PDF_PATH),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle("時間外勤務手当 申請時の確認事項（架空）")
    pdf.setAuthor("RAG Portfolio Fixture Generator")
    pdf.drawImage(
        ImageReader(str(SOURCE_IMAGE_PATH)),
        0,
        0,
        width=PAGE_WIDTH_POINTS,
        height=PAGE_HEIGHT_POINTS,
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
    prefix = RENDERED_IMAGE_PATH.with_suffix("")
    subprocess.run(
        [renderer, "-singlefile", "-png", "-r", "150", str(PDF_PATH), str(prefix)],
        check=True,
    )


def write_gold(regions: list[dict[str, object]]) -> None:
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    gold = {
        "schema_version": "1.0",
        "kind": "scanned_text",
        "title": "時間外勤務手当 申請時の確認事項（架空）",
        "page_count": 1,
        "expected_full_text": expected_text(),
        "critical_values": [
            "2026年6月1日",
            "翌月10日",
            "30,000円以上",
            "5営業日以内",
        ],
        "input_characteristics": {
            "text_layer_expected": False,
            "dpi": SOURCE_DPI,
            "rotation_degrees": 0,
            "quality": "clean",
        },
        "confidence": {
            "source": "unavailable",
            "value": None,
            "review_required": True,
        },
        "pages": [
            {
                "page": 1,
                "width_points": round(PAGE_WIDTH_POINTS, 4),
                "height_points": round(PAGE_HEIGHT_POINTS, 4),
                "source_image_sha256": sha256(SOURCE_IMAGE_PATH),
                "expected_text": expected_text(),
                "regions": regions,
            }
        ],
    }
    GOLD_PATH.write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_manifest() -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_version": "1.0",
        "split": "development",
        "paths_relative_to": "repository_root",
        "generated_by": "eval/text_pdf_fixtures/generate_scan_text_fixture.py",
        "schema": {
            "path": "design/schemas/scan-text-extraction-v1.schema.json",
            "sha256": sha256(SCHEMA_PATH),
        },
        "fixtures": [
            {
                "fixture_id": "scan_text_dev_001",
                "document_family": "overtime_allowance_confirmation_scan_a",
                "kind": "scanned_text",
                "document": {
                    "path": "eval/text_pdf_fixtures/documents/scan_text_dev_001.pdf",
                    "sha256": sha256(PDF_PATH),
                },
                "source_image": {
                    "path": "eval/text_pdf_fixtures/images/scan_text_dev_001_source.png",
                    "sha256": sha256(SOURCE_IMAGE_PATH),
                    "width": SOURCE_WIDTH,
                    "height": SOURCE_HEIGHT,
                    "dpi": SOURCE_DPI,
                },
                "rendered_pages": [
                    {
                        "page": 1,
                        "path": (
                            "eval/text_pdf_fixtures/images/"
                            "scan_text_dev_001_page_001.png"
                        ),
                        "sha256": sha256(RENDERED_IMAGE_PATH),
                    }
                ],
                "gold": {
                    "path": "eval/text_pdf_fixtures/gold/scan_text_dev_001.json",
                    "sha256": sha256(GOLD_PATH),
                },
            }
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    regions = create_source_image()
    create_pdf()
    render_page_image()
    write_gold(regions)
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
