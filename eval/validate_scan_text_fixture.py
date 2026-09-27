"""Validate scanned-text PDF fixture schema, hashes, image input, and OCR contract."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image
import pymupdf

from eval.validate_native_text_fixture import canonical_text
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

    region_ids = []
    page_texts = []
    for page in pages:
        region_texts = []
        for region in page["regions"]:
            region_ids.append(region["id"])
            region_texts.append(region["text"])
            bbox = region["bbox"]
            if bbox["x0"] >= bbox["x1"] or bbox["y0"] >= bbox["y1"]:
                raise ValueError(
                    f"bboxはx0 < x1かつy0 < y1が必要です: {region['id']}"
                )
        regions_text = canonical_text("\n".join(region_texts))
        if regions_text != canonical_text(page["expected_text"]):
            raise ValueError(f"regionsの文字列・順序がpage期待値と一致しません: {page['page']}")
        page_texts.append(page["expected_text"])
    if len(region_ids) != len(set(region_ids)):
        raise ValueError("text region IDが重複しています")
    if canonical_text("\n".join(page_texts)) != canonical_text(
        gold["expected_full_text"]
    ):
        raise ValueError("page期待値がPDF全体の期待全文と一致しません")
    for value in gold["critical_values"]:
        if value not in gold["expected_full_text"]:
            raise ValueError(f"critical valueが期待全文にありません: {value}")


def validate_ocr_candidate(candidate_text: str, gold: dict[str, Any]) -> None:
    """Compare a future OCR candidate with gold without calling an OCR service."""
    for value in gold["critical_values"]:
        if value not in candidate_text:
            raise ValueError(f"OCR候補にcritical valueがありません: {value}")
    if canonical_text(candidate_text) != canonical_text(gold["expected_full_text"]):
        raise ValueError("OCR候補全文がgoldと一致しません")


def validate_source_image(
    image_path: Path, image_entry: dict[str, Any], gold: dict[str, Any]
) -> None:
    with Image.open(image_path) as image:
        if image.size != (image_entry["width"], image_entry["height"]):
            raise ValueError("source image寸法がmanifestと一致しません")
        dpi = image.info.get("dpi")
        if dpi is None or any(abs(value - image_entry["dpi"]) > 0.1 for value in dpi):
            raise ValueError("source imageのdpiがmanifestと一致しません")
    if image_entry["dpi"] != gold["input_characteristics"]["dpi"]:
        raise ValueError("source imageとgoldのdpiが一致しません")
    for page in gold["pages"]:
        if page["source_image_sha256"] != image_entry["sha256"]:
            raise ValueError("goldとsource imageのSHA-256が一致しません")


def validate_document_content(
    document_path: Path, gold: dict[str, Any], source_image: dict[str, Any]
) -> None:
    with pymupdf.open(document_path) as document:
        if document.page_count != gold["page_count"]:
            raise ValueError("PDF page数がgoldと一致しません")
        for page_gold in gold["pages"]:
            page = document[page_gold["page"] - 1]
            if abs(page.rect.width - page_gold["width_points"]) > 0.01:
                raise ValueError(f"page幅がgoldと一致しません: {page_gold['page']}")
            if abs(page.rect.height - page_gold["height_points"]) > 0.01:
                raise ValueError(f"page高さがgoldと一致しません: {page_gold['page']}")
            if page.rotation != gold["input_characteristics"]["rotation_degrees"]:
                raise ValueError(f"page回転角がgoldと一致しません: {page_gold['page']}")
            if page.get_text().strip():
                raise ValueError(f"scan PDFにnative text layerがあります: {page_gold['page']}")
            images = page.get_images(full=True)
            if not images:
                raise ValueError(f"scan PDFに埋め込み画像がありません: {page_gold['page']}")
            expected_size = (source_image["width"], source_image["height"])
            image_sizes = {(entry[2], entry[3]) for entry in images}
            if expected_size not in image_sizes:
                raise ValueError(
                    f"PDF内の画像寸法がsource imageと一致しません: {page_gold['page']}"
                )


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
    if any(not value for value in fixture_ids) or len(fixture_ids) != len(
        set(fixture_ids)
    ):
        raise ValueError("fixture_idは空でない一意な値である必要があります")

    for fixture in fixtures:
        fixture_id = fixture["fixture_id"]
        if fixture["kind"] != "scanned_text":
            raise ValueError(f"kindはscanned_textである必要があります: {fixture_id}")
        document_path = checked_path(repository_root, fixture["document"]["path"])
        verify_hash(document_path, fixture["document"]["sha256"], f"{fixture_id}.document")
        gold_path = checked_path(repository_root, fixture["gold"]["path"])
        verify_hash(gold_path, fixture["gold"]["sha256"], f"{fixture_id}.gold")
        gold = load_json(gold_path)
        validate_gold(gold, schema)

        source_image = fixture["source_image"]
        source_path = checked_path(repository_root, source_image["path"])
        verify_hash(source_path, source_image["sha256"], f"{fixture_id}.source_image")
        validate_source_image(source_path, source_image, gold)

        rendered_pages = fixture.get("rendered_pages")
        if not isinstance(rendered_pages, list) or len(rendered_pages) != gold["page_count"]:
            raise ValueError("rendered_pagesの件数がpage_countと一致しません")
        rendered_page_numbers = [entry["page"] for entry in rendered_pages]
        if rendered_page_numbers != list(range(1, gold["page_count"] + 1)):
            raise ValueError("rendered_pagesはpage順に揃える必要があります")
        for entry in rendered_pages:
            rendered_path = checked_path(repository_root, entry["path"])
            verify_hash(
                rendered_path,
                entry["sha256"],
                f"{fixture_id}.rendered_page_{entry['page']}",
            )
        validate_document_content(document_path, gold, source_image)
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
