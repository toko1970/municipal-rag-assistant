"""Generate a fictional allowance application-form example fixture."""

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

from eval.visual_fixtures.build_development_manifest import (
    MANIFEST_PATH,
    write_development_manifest,
)
from eval.visual_fixtures.generate_flowchart_fixture import (
    find_japanese_font,
    normalized_bbox,
    sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "visual_fixtures"
PDF_PATH = FIXTURE_ROOT / "documents" / "form_dev_001.pdf"
IMAGE_PATH = FIXTURE_ROOT / "images" / "form_dev_001_page_001.png"
GOLD_PATH = FIXTURE_ROOT / "gold" / "form_dev_001.json"
PAGE_WIDTH, PAGE_HEIGHT = A4

FIELDS = (
    ("employee_id", "職員番号", "123456", (42, 185, 270, 250)),
    ("employee_name", "氏名", "給与 花子（架空）", (300, 185, 553, 250)),
    ("effective_date", "異動年月日", "2026年4月1日", (42, 290, 270, 355)),
    ("dependent_name", "扶養親族氏名", "給与 一郎（架空）", (300, 290, 553, 355)),
    ("relationship", "続柄", "子", (42, 395, 270, 460)),
    ("change_reason", "異動理由", "出生", (300, 395, 553, 460)),
    ("attachment", "添付書類", "住民票の写し", (42, 500, 553, 565)),
)


def draw_field(
    pdf: canvas.Canvas,
    label: str,
    value: str,
    box: tuple[float, float, float, float],
) -> None:
    x0, y0, x1, y1 = box
    pdf.setFillColor(HexColor("#E8EEF5"))
    pdf.setStrokeColor(HexColor("#526579"))
    pdf.rect(x0, PAGE_HEIGHT - y0 - 22, x1 - x0, 22, fill=1, stroke=1)
    pdf.setFillColor(HexColor("#243B53"))
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawString(x0 + 8, PAGE_HEIGHT - y0 - 15, label)

    pdf.setFillColor(white)
    pdf.setStrokeColor(HexColor("#526579"))
    pdf.rect(x0, PAGE_HEIGHT - y1, x1 - x0, y1 - y0 - 22, fill=1, stroke=1)
    pdf.setFillColor(HexColor("#172033"))
    pdf.setFont("FixtureJapanese", 10)
    pdf.drawString(x0 + 10, PAGE_HEIGHT - y1 + 16, value)


def create_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    font_path = find_japanese_font()
    pdfmetrics.registerFont(TTFont("FixtureJapanese", str(font_path), subfontIndex=0))
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=A4, pageCompression=1, invariant=1)
    pdf.setTitle("扶養手当認定届 記入例（架空）")
    pdf.setAuthor("RAG Portfolio Fixture Generator")

    pdf.setFillColor(HexColor("#FAFBFD"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#3D5366"))
    pdf.rect(0, PAGE_HEIGHT - 76, PAGE_WIDTH, 76, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("FixtureJapanese", 19)
    pdf.drawString(42, PAGE_HEIGHT - 45, "扶養手当認定届 記入例（架空）")
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawRightString(PAGE_WIDTH - 42, PAGE_HEIGHT - 45, "氏名・番号・日付はすべて架空です")

    pdf.setFillColor(HexColor("#B45309"))
    pdf.setFont("FixtureJapanese", 14)
    pdf.drawString(42, PAGE_HEIGHT - 120, "記入例")
    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 9)
    pdf.drawString(110, PAGE_HEIGHT - 118, "青灰色の見出しごとに記入欄を構造化します。")
    for _, label, value, box in FIELDS:
        draw_field(pdf, label, value, box)

    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawString(42, 40, "注: 本文書はRAG評価専用に作成した架空の申請書記入例です。")
    pdf.drawRightString(PAGE_WIDTH - 42, 40, "1 / 1")
    pdf.showPage()
    pdf.save()


def render_page_image() -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    prefix = IMAGE_PATH.with_name("form_dev_001_page_001")
    subprocess.run(
        [renderer, "-singlefile", "-png", "-r", "150", str(PDF_PATH), str(prefix)],
        check=True,
    )


def write_gold() -> None:
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    gold = {
        "schema_version": "1.0",
        "kind": "form",
        "title": "扶養手当認定届 記入例（架空）",
        "page": 1,
        "bbox": normalized_bbox(38, 155, 557, 580),
        "source_image_sha256": sha256(IMAGE_PATH),
        "confidence": {"source": "unavailable", "value": None, "review_required": True},
        "data": {
            "type": "form",
            "fields": [
                {
                    "id": field_id,
                    "label": label,
                    "example_value": value,
                    "bbox": normalized_bbox(*box),
                }
                for field_id, label, value, box in FIELDS
            ],
        },
    }
    GOLD_PATH.write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    create_pdf()
    render_page_image()
    write_gold()
    write_development_manifest()
    for path in (PDF_PATH, IMAGE_PATH, GOLD_PATH, MANIFEST_PATH):
        print(path.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
