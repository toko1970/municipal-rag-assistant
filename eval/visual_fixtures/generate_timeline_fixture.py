"""Generate a relative-deadline timeline fixture."""

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
PDF_PATH = FIXTURE_ROOT / "documents" / "timeline_dev_001.pdf"
IMAGE_PATH = FIXTURE_ROOT / "images" / "timeline_dev_001_page_001.png"
GOLD_PATH = FIXTURE_ROOT / "gold" / "timeline_dev_001.json"
PAGE_WIDTH, PAGE_HEIGHT = A4

EVENTS = (
    ("change_known", "異動日", "扶養状況の変更を確認", 175),
    ("submit", "翌日から10日以内", "職員が届出書と確認書類を提出", 290),
    ("review", "受領後2営業日以内", "給与担当者が届出内容を確認", 405),
    ("register", "当月給与の締切日まで", "給与システムへ登録", 520),
    ("payment", "翌月給与", "認定した手当額を反映", 635),
)


def draw_event(
    pdf: canvas.Canvas,
    date_or_offset: str,
    action: str,
    y: float,
) -> None:
    date_box = (42, y - 27, 142, y + 27)
    action_box = (188, y - 32, 553, y + 32)

    pdf.setFillColor(HexColor("#E8EEF5"))
    pdf.setStrokeColor(HexColor("#6B7C93"))
    pdf.setLineWidth(1.2)
    pdf.roundRect(
        date_box[0],
        PAGE_HEIGHT - date_box[3],
        date_box[2] - date_box[0],
        date_box[3] - date_box[1],
        8,
        fill=1,
        stroke=1,
    )
    pdf.setFont("FixtureJapanese", 8.3)
    pdf.setFillColor(HexColor("#243B53"))
    pdf.drawCentredString(92, PAGE_HEIGHT - y - 3, date_or_offset)

    pdf.setFillColor(white)
    pdf.setStrokeColor(HexColor("#2F6690"))
    pdf.setLineWidth(1.5)
    pdf.roundRect(
        action_box[0],
        PAGE_HEIGHT - action_box[3],
        action_box[2] - action_box[0],
        action_box[3] - action_box[1],
        12,
        fill=1,
        stroke=1,
    )
    pdf.setFont("FixtureJapanese", 10.5)
    pdf.setFillColor(HexColor("#172033"))
    pdf.drawCentredString((action_box[0] + action_box[2]) / 2, PAGE_HEIGHT - y - 4, action)

    pdf.setFillColor(HexColor("#2F6690"))
    pdf.circle(165, PAGE_HEIGHT - y, 7, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor("#2F6690"))
    pdf.setLineWidth(1.5)
    pdf.line(172, PAGE_HEIGHT - y, 188, PAGE_HEIGHT - y)


def create_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    font_path = find_japanese_font()
    pdfmetrics.registerFont(TTFont("FixtureJapanese", str(font_path), subfontIndex=0))
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=A4, pageCompression=1, invariant=1)
    pdf.setTitle("扶養手当 申請期限タイムライン（架空）")
    pdf.setAuthor("RAG Portfolio Fixture Generator")

    pdf.setFillColor(HexColor("#F7F9FC"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#315B7D"))
    pdf.rect(0, PAGE_HEIGHT - 76, PAGE_WIDTH, 76, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("FixtureJapanese", 19)
    pdf.drawString(42, PAGE_HEIGHT - 45, "扶養手当 申請期限タイムライン（架空）")
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawRightString(PAGE_WIDTH - 42, PAGE_HEIGHT - 45, "期限はすべて評価用の架空設定です")

    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 9)
    pdf.drawString(42, PAGE_HEIGHT - 112, "基準日・相対期限・処理内容を上から順に示します。")

    first_y = EVENTS[0][3]
    last_y = EVENTS[-1][3]
    pdf.setStrokeColor(HexColor("#9FB3C8"))
    pdf.setLineWidth(4)
    pdf.line(165, PAGE_HEIGHT - first_y, 165, PAGE_HEIGHT - last_y)
    for _, date_or_offset, action, y in EVENTS:
        draw_event(pdf, date_or_offset, action, y)

    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawString(42, 40, "注: 本文書はRAG評価専用に作成した架空の期限案内です。")
    pdf.drawRightString(PAGE_WIDTH - 42, 40, "1 / 1")
    pdf.showPage()
    pdf.save()


def render_page_image() -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    prefix = IMAGE_PATH.with_name("timeline_dev_001_page_001")
    subprocess.run(
        [renderer, "-singlefile", "-png", "-r", "150", str(PDF_PATH), str(prefix)],
        check=True,
    )


def write_gold() -> None:
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    gold = {
        "schema_version": "1.0",
        "kind": "timeline",
        "title": "扶養手当 申請期限タイムライン（架空）",
        "page": 1,
        "bbox": normalized_bbox(38, 128, 557, 680),
        "source_image_sha256": sha256(IMAGE_PATH),
        "confidence": {"source": "unavailable", "value": None, "review_required": True},
        "data": {
            "type": "timeline",
            "events": [
                {
                    "id": event_id,
                    "date_or_offset": date_or_offset,
                    "action": action,
                    "bbox": normalized_bbox(42, y - 32, 553, y + 32),
                }
                for event_id, date_or_offset, action, y in EVENTS
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
