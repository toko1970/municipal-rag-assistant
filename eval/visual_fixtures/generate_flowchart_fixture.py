"""Generate the first deterministic visual evaluation fixture.

The PDF is an input document.  The rendered PNG is the page image an
extractor would inspect.  The gold JSON describes the structure that a correct
extractor should recover from that image.
"""

from __future__ import annotations

import hashlib
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "eval" / "visual_fixtures"
PDF_PATH = FIXTURE_ROOT / "documents" / "flowchart_dev_001.pdf"
IMAGE_PATH = FIXTURE_ROOT / "images" / "flowchart_dev_001_page_001.png"
GOLD_PATH = FIXTURE_ROOT / "gold" / "flowchart_dev_001.json"
SCHEMA_PATH = REPOSITORY_ROOT / "design" / "schemas" / "visual-extraction-v1.schema.json"

PAGE_WIDTH, PAGE_HEIGHT = A4


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_bbox(x0: float, y0: float, x1: float, y1: float) -> dict[str, float]:
    """Convert top-left PDF coordinates to the normalized fixture contract."""
    return {
        "x0": round(x0 / PAGE_WIDTH, 4),
        "y0": round(y0 / PAGE_HEIGHT, 4),
        "x1": round(x1 / PAGE_WIDTH, 4),
        "y1": round(y1 / PAGE_HEIGHT, 4),
    }


def find_japanese_font() -> Path:
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("日本語を描画できるfontが見つかりません")


def draw_text_centered(
    pdf: canvas.Canvas,
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    size: int,
    font: str,
) -> None:
    text_y = PAGE_HEIGHT - ((y0 + y1) / 2) - size * 0.35
    pdf.setFont(font, size)
    pdf.setFillColor(HexColor("#172033"))
    pdf.drawCentredString((x0 + x1) / 2, text_y, text)


def draw_round_node(
    pdf: canvas.Canvas,
    bbox: tuple[float, float, float, float],
    text: str,
    *,
    fill: str,
    radius: int = 12,
    font: str,
) -> None:
    x0, y0, x1, y1 = bbox
    pdf.setFillColor(HexColor(fill))
    pdf.setStrokeColor(HexColor("#315B7D"))
    pdf.setLineWidth(1.5)
    pdf.roundRect(x0, PAGE_HEIGHT - y1, x1 - x0, y1 - y0, radius, fill=1, stroke=1)
    draw_text_centered(pdf, text, x0, y0, x1, y1, size=11, font=font)


def draw_diamond(
    pdf: canvas.Canvas,
    bbox: tuple[float, float, float, float],
    text: str,
    *,
    font: str,
) -> None:
    x0, y0, x1, y1 = bbox
    mid_x = (x0 + x1) / 2
    mid_y = (y0 + y1) / 2
    path = pdf.beginPath()
    path.moveTo(mid_x, PAGE_HEIGHT - y0)
    path.lineTo(x1, PAGE_HEIGHT - mid_y)
    path.lineTo(mid_x, PAGE_HEIGHT - y1)
    path.lineTo(x0, PAGE_HEIGHT - mid_y)
    path.close()
    pdf.setFillColor(HexColor("#FFF2CC"))
    pdf.setStrokeColor(HexColor("#9A6A00"))
    pdf.setLineWidth(1.5)
    pdf.drawPath(path, fill=1, stroke=1)
    draw_text_centered(pdf, text, x0, y0, x1, y1, size=11, font=font)


def draw_arrow(
    pdf: canvas.Canvas,
    points: list[tuple[float, float]],
    *,
    label: str | None = None,
    label_position: tuple[float, float] | None = None,
    font: str,
) -> None:
    pdf.setStrokeColor(HexColor("#526579"))
    pdf.setFillColor(HexColor("#526579"))
    pdf.setLineWidth(1.8)
    for start, end in zip(points, points[1:]):
        pdf.line(start[0], PAGE_HEIGHT - start[1], end[0], PAGE_HEIGHT - end[1])
    x, y = points[-1]
    prev_x, prev_y = points[-2]
    if abs(y - prev_y) >= abs(x - prev_x):
        direction = 1 if y > prev_y else -1
        triangle = [(x, y), (x - 5, y - 8 * direction), (x + 5, y - 8 * direction)]
    else:
        direction = 1 if x > prev_x else -1
        triangle = [(x, y), (x - 8 * direction, y - 5), (x - 8 * direction, y + 5)]
    path = pdf.beginPath()
    path.moveTo(triangle[0][0], PAGE_HEIGHT - triangle[0][1])
    for point in triangle[1:]:
        path.lineTo(point[0], PAGE_HEIGHT - point[1])
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)
    if label and label_position:
        pdf.setFont(font, 10)
        pdf.setFillColor(HexColor("#334155"))
        pdf.drawString(label_position[0], PAGE_HEIGHT - label_position[1], label)


def create_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    font_path = find_japanese_font()
    pdfmetrics.registerFont(TTFont("FixtureJapanese", str(font_path), subfontIndex=0))

    pdf = canvas.Canvas(
        str(PDF_PATH),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle("通勤手当 申請処理フロー（架空）")
    pdf.setAuthor("RAG Portfolio Fixture Generator")

    pdf.setFillColor(HexColor("#F5F8FC"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#173B57"))
    pdf.rect(0, PAGE_HEIGHT - 76, PAGE_WIDTH, 76, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("FixtureJapanese", 19)
    pdf.drawString(42, PAGE_HEIGHT - 45, "通勤手当 申請処理フロー（架空）")
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawRightString(PAGE_WIDTH - 42, PAGE_HEIGHT - 45, "評価用fixture / 個人情報を含みません")

    nodes = {
        "start": (205, 112, 390, 162),
        "check": (165, 210, 430, 276),
        "decision": (205, 335, 390, 435),
        "return": (55, 505, 215, 571),
        "register": (365, 505, 540, 571),
        "end": (365, 675, 540, 725),
    }

    draw_round_node(pdf, nodes["start"], "申請書を受領", fill="#D9EAF7", radius=24, font="FixtureJapanese")
    draw_round_node(pdf, nodes["check"], "記載内容・添付書類を確認", fill="#E7F1FA", font="FixtureJapanese")
    draw_diamond(pdf, nodes["decision"], "不備があるか", font="FixtureJapanese")
    draw_round_node(pdf, nodes["return"], "申請者へ差戻し", fill="#FCE8E6", font="FixtureJapanese")
    draw_round_node(pdf, nodes["register"], "給与システムへ登録", fill="#E8F5E9", font="FixtureJapanese")
    draw_round_node(pdf, nodes["end"], "処理完了", fill="#D9EAD3", radius=24, font="FixtureJapanese")

    draw_arrow(pdf, [(297.5, 162), (297.5, 210)], font="FixtureJapanese")
    draw_arrow(pdf, [(297.5, 276), (297.5, 335)], font="FixtureJapanese")
    draw_arrow(
        pdf,
        [(205, 385), (135, 385), (135, 505)],
        label="あり",
        label_position=(151, 375),
        font="FixtureJapanese",
    )
    draw_arrow(
        pdf,
        [(135, 505), (42, 505), (42, 243), (165, 243)],
        label="再提出",
        label_position=(48, 494),
        font="FixtureJapanese",
    )
    draw_arrow(
        pdf,
        [(390, 385), (452.5, 385), (452.5, 505)],
        label="なし",
        label_position=(407, 375),
        font="FixtureJapanese",
    )
    draw_arrow(pdf, [(452.5, 571), (452.5, 675)], font="FixtureJapanese")

    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawString(42, 40, "注: 本文書はRAG評価専用に作成した架空の業務フローです。")
    pdf.drawRightString(PAGE_WIDTH - 42, 40, "1 / 1")
    pdf.showPage()
    pdf.save()


def render_page_image() -> None:
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    prefix = IMAGE_PATH.with_name("flowchart_dev_001_page_001")
    subprocess.run(
        [renderer, "-singlefile", "-png", "-r", "150", str(PDF_PATH), str(prefix)],
        check=True,
    )


def write_gold() -> None:
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    nodes = {
        "start": (205, 112, 390, 162),
        "check": (165, 210, 430, 276),
        "decision": (205, 335, 390, 435),
        "return": (55, 505, 215, 571),
        "register": (365, 505, 540, 571),
        "end": (365, 675, 540, 725),
    }
    gold = {
        "schema_version": "1.0",
        "kind": "flowchart",
        "title": "通勤手当 申請処理フロー（架空）",
        "page": 1,
        "bbox": normalized_bbox(42, 92, 552, 742),
        "source_image_sha256": sha256(IMAGE_PATH),
        "confidence": {
            "source": "unavailable",
            "value": None,
            "review_required": True,
        },
        "data": {
            "type": "flowchart",
            "nodes": [
                {"id": "start", "text": "申請書を受領", "node_type": "start", "bbox": normalized_bbox(*nodes["start"])},
                {"id": "check", "text": "記載内容・添付書類を確認", "node_type": "process", "bbox": normalized_bbox(*nodes["check"])},
                {"id": "decision", "text": "不備があるか", "node_type": "decision", "bbox": normalized_bbox(*nodes["decision"])},
                {"id": "return", "text": "申請者へ差戻し", "node_type": "process", "bbox": normalized_bbox(*nodes["return"])},
                {"id": "register", "text": "給与システムへ登録", "node_type": "process", "bbox": normalized_bbox(*nodes["register"])},
                {"id": "end", "text": "処理完了", "node_type": "end", "bbox": normalized_bbox(*nodes["end"])},
            ],
            "edges": [
                {"from": "start", "to": "check", "condition": None, "bbox": normalized_bbox(290, 162, 305, 210)},
                {"from": "check", "to": "decision", "condition": None, "bbox": normalized_bbox(290, 276, 305, 335)},
                {"from": "decision", "to": "return", "condition": "あり", "bbox": normalized_bbox(128, 378, 205, 505)},
                {"from": "return", "to": "check", "condition": "再提出", "bbox": normalized_bbox(36, 236, 165, 512)},
                {"from": "decision", "to": "register", "condition": "なし", "bbox": normalized_bbox(390, 378, 460, 505)},
                {"from": "register", "to": "end", "condition": None, "bbox": normalized_bbox(445, 571, 460, 675)},
            ],
        },
    }
    GOLD_PATH.write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    create_pdf()
    render_page_image()
    write_gold()
    write_development_manifest()
    print(PDF_PATH.relative_to(REPOSITORY_ROOT))
    print(IMAGE_PATH.relative_to(REPOSITORY_ROOT))
    print(GOLD_PATH.relative_to(REPOSITORY_ROOT))
    print(MANIFEST_PATH.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
