"""Generate amount and revision-comparison table fixtures."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

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
PAGE_WIDTH, PAGE_HEIGHT = A4


def draw_header(pdf: canvas.Canvas, title: str, note: str) -> None:
    pdf.setFillColor(HexColor("#F7F9FC"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#244A64"))
    pdf.rect(0, PAGE_HEIGHT - 76, PAGE_WIDTH, 76, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("FixtureJapanese", 18)
    pdf.drawString(42, PAGE_HEIGHT - 45, title)
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawRightString(PAGE_WIDTH - 42, PAGE_HEIGHT - 45, note)


def draw_cell(pdf: canvas.Canvas, cell: dict[str, Any], *, header: bool = False) -> None:
    x0, y0, x1, y1 = cell["box"]
    pdf.setFillColor(HexColor("#DCEAF4" if header else "#FFFFFF"))
    pdf.setStrokeColor(HexColor("#46647F"))
    pdf.setLineWidth(1.1)
    pdf.rect(x0, PAGE_HEIGHT - y1, x1 - x0, y1 - y0, fill=1, stroke=1)
    pdf.setFillColor(HexColor("#172033"))
    pdf.setFont("FixtureJapanese", 8.4 if len(cell["text"]) > 12 else 9.5)
    pdf.drawCentredString((x0 + x1) / 2, PAGE_HEIGHT - ((y0 + y1) / 2) - 3, cell["text"])


def table_cells_amount() -> list[dict[str, Any]]:
    xs = (42, 142, 272, 382, 553)
    ys = (190, 250, 310, 370, 430)
    values = [
        (0, 0, 1, 1, "職員区分", (xs[0], ys[0], xs[1], ys[1]), True),
        (0, 1, 1, 1, "通勤回数", (xs[1], ys[0], xs[2], ys[1]), True),
        (0, 2, 1, 1, "月額", (xs[2], ys[0], xs[3], ys[1]), True),
        (0, 3, 1, 1, "備考", (xs[3], ys[0], xs[4], ys[1]), True),
        (1, 0, 2, 1, "常勤職員", (xs[0], ys[1], xs[1], ys[3]), False),
        (1, 1, 1, 1, "月15日以上", (xs[1], ys[1], xs[2], ys[2]), False),
        (1, 2, 1, 1, "12,000円", (xs[2], ys[1], xs[3], ys[2]), False),
        (1, 3, 1, 1, "上限額", (xs[3], ys[1], xs[4], ys[2]), False),
        (2, 1, 1, 1, "月8〜14日", (xs[1], ys[2], xs[2], ys[3]), False),
        (2, 2, 1, 1, "8,000円", (xs[2], ys[2], xs[3], ys[3]), False),
        (2, 3, 1, 1, "日数に応じる", (xs[3], ys[2], xs[4], ys[3]), False),
        (3, 0, 1, 1, "短時間職員", (xs[0], ys[3], xs[1], ys[4]), False),
        (3, 1, 1, 1, "月1〜7日", (xs[1], ys[3], xs[2], ys[4]), False),
        (3, 2, 1, 1, "4,000円", (xs[2], ys[3], xs[3], ys[4]), False),
        (3, 3, 1, 1, "最低区分", (xs[3], ys[3], xs[4], ys[4]), False),
    ]
    return [
        {
            "row": row,
            "column": column,
            "row_span": row_span,
            "column_span": column_span,
            "text": text,
            "box": box,
            "header": header,
        }
        for row, column, row_span, column_span, text, box, header in values
    ]


def table_cells_revision() -> list[dict[str, Any]]:
    xs = (42, 142, 242, 352, 452, 553)
    ys = (175, 225, 275, 335, 395, 455)
    values = [
        (0, 0, 2, 1, "項目", (xs[0], ys[0], xs[1], ys[2]), True),
        (0, 1, 1, 2, "改定前", (xs[1], ys[0], xs[3], ys[1]), True),
        (0, 3, 1, 2, "改定後", (xs[3], ys[0], xs[5], ys[1]), True),
        (1, 1, 1, 1, "金額", (xs[1], ys[1], xs[2], ys[2]), True),
        (1, 2, 1, 1, "条件", (xs[2], ys[1], xs[3], ys[2]), True),
        (1, 3, 1, 1, "金額", (xs[3], ys[1], xs[4], ys[2]), True),
        (1, 4, 1, 1, "条件", (xs[4], ys[1], xs[5], ys[2]), True),
        (2, 0, 1, 1, "住居手当", (xs[0], ys[2], xs[1], ys[3]), False),
        (2, 1, 1, 1, "10,000円", (xs[1], ys[2], xs[2], ys[3]), False),
        (2, 2, 1, 1, "要件A", (xs[2], ys[2], xs[3], ys[3]), False),
        (2, 3, 1, 1, "12,000円", (xs[3], ys[2], xs[4], ys[3]), False),
        (2, 4, 1, 1, "要件B", (xs[4], ys[2], xs[5], ys[3]), False),
        (3, 0, 1, 1, "通勤手当", (xs[0], ys[3], xs[1], ys[4]), False),
        (3, 1, 1, 1, "8,000円", (xs[1], ys[3], xs[2], ys[4]), False),
        (3, 2, 1, 1, "月8日以上", (xs[2], ys[3], xs[3], ys[4]), False),
        (3, 3, 1, 1, "9,000円", (xs[3], ys[3], xs[4], ys[4]), False),
        (3, 4, 1, 1, "月6日以上", (xs[4], ys[3], xs[5], ys[4]), False),
        (4, 0, 1, 1, "施行日", (xs[0], ys[4], xs[1], ys[5]), True),
        (4, 1, 1, 4, "2026年4月1日", (xs[1], ys[4], xs[5], ys[5]), False),
    ]
    return [
        {
            "row": row,
            "column": column,
            "row_span": row_span,
            "column_span": column_span,
            "text": text,
            "box": box,
            "header": header,
        }
        for row, column, row_span, column_span, text, box, header in values
    ]


def create_table_fixture(
    fixture_name: str,
    title: str,
    row_count: int,
    column_count: int,
    cells: list[dict[str, Any]],
) -> tuple[Path, Path, Path]:
    pdf_path = FIXTURE_ROOT / "documents" / f"{fixture_name}.pdf"
    image_path = FIXTURE_ROOT / "images" / f"{fixture_name}_page_001.png"
    gold_path = FIXTURE_ROOT / "gold" / f"{fixture_name}.json"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    font_path = find_japanese_font()
    pdfmetrics.registerFont(TTFont("FixtureJapanese", str(font_path), subfontIndex=0))
    pdf = canvas.Canvas(str(pdf_path), pagesize=A4, pageCompression=1, invariant=1)
    pdf.setTitle(title)
    pdf.setAuthor("RAG Portfolio Fixture Generator")
    draw_header(pdf, title, "評価用fixture / 金額・条件は架空です")
    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 9)
    pdf.drawString(42, PAGE_HEIGHT - 112, "結合cellを含む表として構造化します。")
    for cell in cells:
        draw_cell(pdf, cell, header=cell["header"])
    pdf.setFillColor(HexColor("#536273"))
    pdf.setFont("FixtureJapanese", 8.5)
    pdf.drawString(42, 40, "注: 本文書はRAG評価専用に作成した架空の表です。")
    pdf.drawRightString(PAGE_WIDTH - 42, 40, "1 / 1")
    pdf.showPage()
    pdf.save()

    image_path.parent.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppmが見つかりません")
    prefix = image_path.with_name(f"{fixture_name}_page_001")
    subprocess.run(
        [renderer, "-singlefile", "-png", "-r", "150", str(pdf_path), str(prefix)],
        check=True,
    )

    gold_path.parent.mkdir(parents=True, exist_ok=True)
    table_bbox = (
        min(cell["box"][0] for cell in cells),
        min(cell["box"][1] for cell in cells),
        max(cell["box"][2] for cell in cells),
        max(cell["box"][3] for cell in cells),
    )
    gold = {
        "schema_version": "1.0",
        "kind": "table",
        "title": title,
        "page": 1,
        "bbox": normalized_bbox(*table_bbox),
        "source_image_sha256": sha256(image_path),
        "confidence": {"source": "unavailable", "value": None, "review_required": True},
        "data": {
            "type": "table",
            "row_count": row_count,
            "column_count": column_count,
            "cells": [
                {
                    "row": cell["row"],
                    "column": cell["column"],
                    "row_span": cell["row_span"],
                    "column_span": cell["column_span"],
                    "text": cell["text"],
                    "bbox": normalized_bbox(*cell["box"]),
                }
                for cell in cells
            ],
        },
    }
    gold_path.write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pdf_path, image_path, gold_path


def main() -> None:
    paths = []
    paths.extend(
        create_table_fixture(
            "table_dev_001",
            "通勤手当 支給額・区分表（架空）",
            4,
            4,
            table_cells_amount(),
        )
    )
    paths.extend(
        create_table_fixture(
            "table_dev_002",
            "手当制度 改定前後比較（架空）",
            5,
            5,
            table_cells_revision(),
        )
    )
    write_development_manifest()
    for path in (*paths, MANIFEST_PATH):
        print(path.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
