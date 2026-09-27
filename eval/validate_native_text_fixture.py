"""Validate native-text PDF fixture schema, hashes, text layer, and positions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import pymupdf

from eval.validate_visual_fixture import checked_path, load_json, verify_hash


def schema_errors(instance: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: list(error.path),
    )
    return [
        f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
        for error in errors
    ]


def validate_gold(gold: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = schema_errors(gold, schema)
    if errors:
        raise ValueError("Schema validationに失敗しました:\n" + "\n".join(errors))
    pages = gold["pages"]
    if len(pages) != gold["page_count"]:
        raise ValueError("pagesの件数がpage_countと一致しません")
    page_numbers = [page["page"] for page in pages]
    if page_numbers != list(range(1, gold["page_count"] + 1)):
        raise ValueError("pageは1からpage_countまでの順序で固定します")
    block_ids = []
    for page in pages:
        for block in page["blocks"]:
            block_ids.append(block["id"])
            bbox = block["bbox"]
            if bbox["x0"] >= bbox["x1"] or bbox["y0"] >= bbox["y1"]:
                raise ValueError(f"bboxはx0 < x1かつy0 < y1が必要です: {block['id']}")
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("text block IDが重複しています")
    for value in gold["critical_values"]:
        if value not in gold["expected_full_text"]:
            raise ValueError(f"critical valueが期待全文にありません: {value}")


def canonical_text(text: str) -> str:
    """Ignore parser-added blank lines and indentation, preserving text and order."""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def extracted_page_text(page: pymupdf.Page) -> str:
    return canonical_text(page.get_text("text", sort=True))


def normalized_rect(rect: pymupdf.Rect, page: pymupdf.Page) -> dict[str, float]:
    return {
        "x0": rect.x0 / page.rect.width,
        "y0": rect.y0 / page.rect.height,
        "x1": rect.x1 / page.rect.width,
        "y1": rect.y1 / page.rect.height,
    }


def bbox_contains(expected: dict[str, float], actual: dict[str, float]) -> bool:
    tolerance = 0.005
    return (
        expected["x0"] - tolerance <= actual["x0"]
        and expected["y0"] - tolerance <= actual["y0"]
        and expected["x1"] + tolerance >= actual["x1"]
        and expected["y1"] + tolerance >= actual["y1"]
    )


def validate_document_content(document_path: Path, gold: dict[str, Any]) -> None:
    with pymupdf.open(document_path) as document:
        if document.page_count != gold["page_count"]:
            raise ValueError("PDF page数がgoldと一致しません")
        extracted_pages = []
        for page_gold in gold["pages"]:
            page = document[page_gold["page"] - 1]
            if abs(page.rect.width - page_gold["width_points"]) > 0.01:
                raise ValueError(f"page幅がgoldと一致しません: {page_gold['page']}")
            if abs(page.rect.height - page_gold["height_points"]) > 0.01:
                raise ValueError(f"page高さがgoldと一致しません: {page_gold['page']}")
            text = extracted_page_text(page)
            if not text.strip():
                raise ValueError(f"native text layerが空です: page {page_gold['page']}")
            if text != canonical_text(page_gold["expected_text"]):
                raise ValueError(f"抽出全文がgoldと一致しません: page {page_gold['page']}")
            extracted_pages.append(text)
            for block in page_gold["blocks"]:
                matches = page.search_for(block["text"])
                if len(matches) != 1:
                    raise ValueError(
                        f"text blockが一意に見つかりません: {block['id']} / {len(matches)}"
                    )
                actual_bbox = normalized_rect(matches[0], page)
                if not bbox_contains(block["bbox"], actual_bbox):
                    raise ValueError(f"text blockがgold bboxの範囲外です: {block['id']}")
        full_text = "\n".join(extracted_pages)
        if full_text != canonical_text(gold["expected_full_text"]):
            raise ValueError("PDF全体の抽出全文がgoldと一致しません")
        for value in gold["critical_values"]:
            if value not in full_text:
                raise ValueError(f"critical valueを抽出できません: {value}")


def validate_manifest(manifest_path: Path, repository_root: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    if manifest.get("split") != "development":
        raise ValueError("splitはdevelopmentである必要があります")
    if manifest.get("paths_relative_to") != "repository_root":
        raise ValueError("paths_relative_toはrepository_rootである必要があります")
    schema_entry = manifest.get("schema")
    if not isinstance(schema_entry, dict):
        raise ValueError("schema entryがありません")
    schema_path = checked_path(repository_root, schema_entry["path"])
    verify_hash(schema_path, schema_entry["sha256"], "schema")
    schema = load_json(schema_path)

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("fixturesが空です")
    fixture_ids = [fixture.get("fixture_id") for fixture in fixtures]
    if any(not value for value in fixture_ids) or len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("fixture_idは空でない一意な値である必要があります")

    for fixture in fixtures:
        fixture_id = fixture["fixture_id"]
        if fixture["kind"] != "native_text":
            raise ValueError(f"kindはnative_textである必要があります: {fixture_id}")
        document_path = checked_path(repository_root, fixture["document"]["path"])
        verify_hash(document_path, fixture["document"]["sha256"], f"{fixture_id}.document")
        gold_path = checked_path(repository_root, fixture["gold"]["path"])
        verify_hash(gold_path, fixture["gold"]["sha256"], f"{fixture_id}.gold")
        gold = load_json(gold_path)
        validate_gold(gold, schema)

        images_by_page = {}
        for image in fixture["source_images"]:
            page_number = image["page"]
            if page_number in images_by_page:
                raise ValueError(f"source image pageが重複しています: {fixture_id}")
            image_path = checked_path(repository_root, image["path"])
            verify_hash(image_path, image["sha256"], f"{fixture_id}.source_image")
            images_by_page[page_number] = image
        for page_gold in gold["pages"]:
            image = images_by_page.get(page_gold["page"])
            if image is None:
                raise ValueError(f"gold pageに対応するsource imageがありません: {fixture_id}")
            if page_gold["source_image_sha256"] != image["sha256"]:
                raise ValueError(f"goldとsource imageのSHA-256が一致しません: {fixture_id}")
        validate_document_content(document_path, gold)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    manifest = validate_manifest(args.manifest, args.repository_root.resolve())
    print(f"validated split={manifest['split']} fixtures={len(manifest['fixtures'])}")


if __name__ == "__main__":
    main()
