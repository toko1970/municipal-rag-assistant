"""Generate one deterministic native-text PDF fixture and its gold annotation."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from eval.visual_fixtures.generate_flowchart_fixture import (
    find_japanese_font,
    normalized_bbox,
    sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "text_pdf_fixtures"
PDF_PATH = FIXTURE_ROOT / "documents" / "native_text_dev_001.pdf"
IMAGE_PATH = FIXTURE_ROOT / "images" / "native_text_dev_001_page_001.png"
GOLD_PATH = FIXTURE_ROOT / "gold" / "native_text_dev_001.json"
MANIFEST_PATH = FIXTURE_ROOT / "manifests" / "development_manifest.json"
SCHEMA_PATH = REPOSITORY_ROOT / "design" / "schemas" / "native-text-extraction-v1.schema.json"
PAGE_WIDTH, PAGE_HEIGHT = A4
FONT_NAME = "NativeTextFixtureJapanese"

TEXT_BLOCKS = (
    ("title", "勤務実績修正届 処理要領（架空）", 54, 770, 18),
    ("document_meta", "文書番号: 架空人給第17号　施行日: 2026年4月1日", 54, 738, 9),
    ("purpose_heading", "1. 目的", 54, 682, 13),
    ("purpose", "本要領は、勤務実績の登録誤りを給与計算前に修正する手順を定める。", 54, 654, 10.5),
    ("deadline_heading", "2. 提出期限", 54, 602, 13),
    ("deadline", "所属の給与事務担当者は、修正対象月の翌月5日までに提出する。", 54, 574, 10.5),
    ("attachments_heading", "3. 必要書類", 54, 522, 13),
    ("attachment_1", "・勤務実績修正届", 70, 494, 10.5),
    ("attachment_2", "・所属長確認書", 70, 468, 10.5),
    ("processing_heading", "4. 処理", 54, 416, 13),
    ("processing", "人事給与課は受付後3営業日以内に内容を確認し、結果を所属へ通知する。", 54, 388, 10.5),
    ("note", "注: 本文書はRAG評価専用の架空資料であり、実在の制度ではない。", 54, 90, 9),
)


def block_bbox(text: str, x: float, baseline_y: float, size: float) -> dict[str, float]:
    width = pdfmetrics.stringWidth(text, FONT_NAME, size)
    top = PAGE_HEIGHT - baseline_y - size - 2
    bottom = PAGE_HEIGHT - baseline_y + 3
    return normalized_bbox(x - 2, top, x + width + 2, bottom)


def expected_text() -> str:
    return "\n".join(block[1] for block in TEXT_BLOCKS)


def create_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    font_path = find_japanese_font()
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path), subfontIndex=0))
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=A4, pageCompression=1, invariant=1)
    pdf.setTitle("勤務実績修正届 処理要領（架空）")
    pdf.setAuthor("RAG Portfolio Fixture Generator")

    pdf.setFillColor(HexColor("#F7F9FC"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#243B53"))
    pdf.rect(0, PAGE_HEIGHT - 92, PAGE_WIDTH, 92, fill=1, stroke=0)

    for block_id, text, x, baseline_y, size in TEXT_BLOCKS:
        pdf.setFont(FONT_NAME, size)
        if block_id == "title":
            pdf.setFillColor(white)
        elif block_id.endswith("heading"):
            pdf.setFillColor(HexColor("#174A6E"))
        else:
            pdf.setFillColor(HexColor("#172033"))
        pdf.drawString(x, baseline_y, text)

    pdf.showPage()
    pdf.save()


def render_page_image() -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    prefix = IMAGE_PATH.with_name("native_text_dev_001_page_001")
    subprocess.run(
        [renderer, "-singlefile", "-png", "-r", "150", str(PDF_PATH), str(prefix)],
        check=True,
    )


def write_gold() -> None:
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    blocks = [
        {
            "id": block_id,
            "text": text,
            "bbox": block_bbox(text, x, baseline_y, size),
        }
        for block_id, text, x, baseline_y, size in TEXT_BLOCKS
    ]
    gold = {
        "schema_version": "1.0",
        "kind": "native_text",
        "title": "勤務実績修正届 処理要領（架空）",
        "page_count": 1,
        "expected_full_text": expected_text(),
        "critical_values": ["2026年4月1日", "翌月5日", "3営業日以内"],
        "confidence": {
            "source": "native_text_layer",
            "value": 1.0,
            "review_required": False,
        },
        "pages": [
            {
                "page": 1,
                "width_points": round(PAGE_WIDTH, 4),
                "height_points": round(PAGE_HEIGHT, 4),
                "source_image_sha256": sha256(IMAGE_PATH),
                "expected_text": expected_text(),
                "blocks": blocks,
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
        "generated_by": "eval/text_pdf_fixtures/generate_native_text_fixture.py",
        "schema": {
            "path": "design/schemas/native-text-extraction-v1.schema.json",
            "sha256": sha256(SCHEMA_PATH),
        },
        "fixtures": [
            {
                "fixture_id": "native_text_dev_001",
                "document_family": "attendance_correction_procedure_native_a",
                "kind": "native_text",
                "document": {
                    "path": "eval/text_pdf_fixtures/documents/native_text_dev_001.pdf",
                    "sha256": sha256(PDF_PATH),
                },
                "source_images": [
                    {
                        "page": 1,
                        "path": "eval/text_pdf_fixtures/images/native_text_dev_001_page_001.png",
                        "sha256": sha256(IMAGE_PATH),
                    }
                ],
                "gold": {
                    "path": "eval/text_pdf_fixtures/gold/native_text_dev_001.json",
                    "sha256": sha256(GOLD_PATH),
                },
            }
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    create_pdf()
    render_page_image()
    write_gold()
    write_manifest()
    for path in (PDF_PATH, IMAGE_PATH, GOLD_PATH, MANIFEST_PATH):
        print(path.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
