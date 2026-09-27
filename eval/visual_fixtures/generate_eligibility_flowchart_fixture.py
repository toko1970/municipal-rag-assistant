"""Generate a branching allowance-eligibility flowchart fixture."""

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
    draw_arrow,
    draw_diamond,
    draw_round_node,
    find_japanese_font,
    normalized_bbox,
    sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "visual_fixtures"
PDF_PATH = FIXTURE_ROOT / "documents" / "flowchart_dev_002.pdf"
IMAGE_PATH = FIXTURE_ROOT / "images" / "flowchart_dev_002_page_001.png"
GOLD_PATH = FIXTURE_ROOT / "gold" / "flowchart_dev_002.json"
PAGE_WIDTH, PAGE_HEIGHT = A4

NODES = {
    "start": (205, 102, 390, 150),
    "employee": (205, 185, 390, 275),
    "documents": (205, 320, 390, 410),
    "requirements": (205, 455, 390, 545),
    "not_eligible": (42, 680, 198, 736),
    "request_documents": (220, 680, 375, 736),
    "eligible": (397, 680, 553, 736),
}


def create_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    font_path = find_japanese_font()
    pdfmetrics.registerFont(TTFont("FixtureJapanese", str(font_path), subfontIndex=0))
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=A4, pageCompression=1, invariant=1)
    pdf.setTitle("住居手当 支給可否判断フロー（架空）")
    pdf.setAuthor("RAG Portfolio Fixture Generator")

    pdf.setFillColor(HexColor("#F7F9FC"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#243B53"))
    pdf.rect(0, PAGE_HEIGHT - 76, PAGE_WIDTH, 76, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("FixtureJapanese", 19)
    pdf.drawString(42, PAGE_HEIGHT - 45, "住居手当 支給可否判断フロー（架空）")
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawRightString(PAGE_WIDTH - 42, PAGE_HEIGHT - 45, "評価用fixture / 個人情報を含みません")

    draw_round_node(pdf, NODES["start"], "申請内容を確認", fill="#D9EAF7", radius=24, font="FixtureJapanese")
    draw_diamond(pdf, NODES["employee"], "対象職員か", font="FixtureJapanese")
    draw_diamond(pdf, NODES["documents"], "必要書類が揃っているか", font="FixtureJapanese")
    draw_diamond(pdf, NODES["requirements"], "支給要件を満たすか", font="FixtureJapanese")
    draw_round_node(pdf, NODES["not_eligible"], "支給対象外", fill="#FCE8E6", radius=24, font="FixtureJapanese")
    draw_round_node(pdf, NODES["request_documents"], "追加提出を依頼", fill="#FFF2CC", radius=24, font="FixtureJapanese")
    draw_round_node(pdf, NODES["eligible"], "支給対象", fill="#D9EAD3", radius=24, font="FixtureJapanese")

    draw_arrow(pdf, [(297.5, 150), (297.5, 185)], font="FixtureJapanese")
    draw_arrow(
        pdf,
        [(205, 230), (120, 230), (120, 680)],
        label="いいえ",
        label_position=(137, 220),
        font="FixtureJapanese",
    )
    draw_arrow(
        pdf,
        [(297.5, 275), (297.5, 320)],
        label="はい",
        label_position=(306, 302),
        font="FixtureJapanese",
    )
    draw_arrow(
        pdf,
        [(390, 365), (455, 365), (455, 620), (297.5, 620), (297.5, 680)],
        label="いいえ",
        label_position=(407, 355),
        font="FixtureJapanese",
    )
    draw_arrow(
        pdf,
        [(297.5, 410), (297.5, 455)],
        label="はい",
        label_position=(306, 437),
        font="FixtureJapanese",
    )
    draw_arrow(
        pdf,
        [(205, 500), (120, 500), (120, 680)],
        label="いいえ",
        label_position=(137, 490),
        font="FixtureJapanese",
    )
    draw_arrow(
        pdf,
        [(390, 500), (475, 500), (475, 680)],
        label="はい",
        label_position=(407, 490),
        font="FixtureJapanese",
    )

    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawString(42, 40, "注: 本文書はRAG評価専用に作成した架空の判断フローです。")
    pdf.drawRightString(PAGE_WIDTH - 42, 40, "1 / 1")
    pdf.showPage()
    pdf.save()


def render_page_image() -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    prefix = IMAGE_PATH.with_name("flowchart_dev_002_page_001")
    subprocess.run(
        [renderer, "-singlefile", "-png", "-r", "150", str(PDF_PATH), str(prefix)],
        check=True,
    )


def write_gold() -> None:
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    gold = {
        "schema_version": "1.0",
        "kind": "flowchart",
        "title": "住居手当 支給可否判断フロー（架空）",
        "page": 1,
        "bbox": normalized_bbox(38, 88, 557, 750),
        "source_image_sha256": sha256(IMAGE_PATH),
        "confidence": {"source": "unavailable", "value": None, "review_required": True},
        "data": {
            "type": "flowchart",
            "nodes": [
                {"id": "start", "text": "申請内容を確認", "node_type": "start", "bbox": normalized_bbox(*NODES["start"])},
                {"id": "employee", "text": "対象職員か", "node_type": "decision", "bbox": normalized_bbox(*NODES["employee"])},
                {"id": "documents", "text": "必要書類が揃っているか", "node_type": "decision", "bbox": normalized_bbox(*NODES["documents"])},
                {"id": "requirements", "text": "支給要件を満たすか", "node_type": "decision", "bbox": normalized_bbox(*NODES["requirements"])},
                {"id": "not_eligible", "text": "支給対象外", "node_type": "end", "bbox": normalized_bbox(*NODES["not_eligible"])},
                {"id": "request_documents", "text": "追加提出を依頼", "node_type": "end", "bbox": normalized_bbox(*NODES["request_documents"])},
                {"id": "eligible", "text": "支給対象", "node_type": "end", "bbox": normalized_bbox(*NODES["eligible"])},
            ],
            "edges": [
                {"from": "start", "to": "employee", "condition": None, "bbox": normalized_bbox(290, 150, 305, 185)},
                {"from": "employee", "to": "not_eligible", "condition": "いいえ", "bbox": normalized_bbox(112, 223, 205, 680)},
                {"from": "employee", "to": "documents", "condition": "はい", "bbox": normalized_bbox(290, 275, 320, 320)},
                {"from": "documents", "to": "request_documents", "condition": "いいえ", "bbox": normalized_bbox(290, 358, 462, 680)},
                {"from": "documents", "to": "requirements", "condition": "はい", "bbox": normalized_bbox(290, 410, 320, 455)},
                {"from": "requirements", "to": "not_eligible", "condition": "いいえ", "bbox": normalized_bbox(112, 493, 205, 680)},
                {"from": "requirements", "to": "eligible", "condition": "はい", "bbox": normalized_bbox(390, 493, 483, 680)},
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
