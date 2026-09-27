"""Validate the low-contrast scan fixture and its mandatory review gate."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image
import pymupdf

from eval.validate_native_text_fixture import canonical_text
from eval.validate_scan_text_fixture import validate_manifest as validate_scan_manifest
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


def grayscale_dynamic_range(image: Image.Image) -> int:
    minimum, maximum = image.convert("L").getextrema()
    return maximum - minimum


def validate_gold(gold: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = schema_errors(gold, schema)
    if errors:
        raise ValueError("Schema validationに失敗しました:\n" + "\n".join(errors))
    page = gold["pages"][0]
    region_ids = []
    region_texts = []
    for region in page["regions"]:
        region_ids.append(region["id"])
        region_texts.append(region["text"])
        bbox = region["bbox"]
        if bbox["x0"] >= bbox["x1"] or bbox["y0"] >= bbox["y1"]:
            raise ValueError(f"bboxはx0 < x1かつy0 < y1が必要です: {region['id']}")
    if len(region_ids) != len(set(region_ids)):
        raise ValueError("text region IDが重複しています")
    if canonical_text("\n".join(region_texts)) != canonical_text(
        page["expected_text"]
    ):
        raise ValueError("regionsの文字列・順序がpage期待値と一致しません")
    if canonical_text(page["expected_text"]) != canonical_text(
        gold["expected_full_text"]
    ):
        raise ValueError("page期待値がPDF全体の期待全文と一致しません")
    for value in gold["critical_values"]:
        if value not in gold["expected_full_text"]:
            raise ValueError(f"critical valueが期待全文にありません: {value}")


def validate_image_quality(
    image_path: Path,
    image_entry: dict[str, Any],
    gold: dict[str, Any],
    clean_dynamic_range: int,
) -> None:
    with Image.open(image_path) as image:
        if image.size != (image_entry["width"], image_entry["height"]):
            raise ValueError("low-quality source image寸法がmanifestと一致しません")
        dpi = image.info.get("dpi")
        if dpi is None or any(abs(value - image_entry["dpi"]) > 0.1 for value in dpi):
            raise ValueError("low-quality source imageのdpiがmanifestと一致しません")
        measured_range = grayscale_dynamic_range(image)

    measurement = gold["quality_assessment"]["measurement"]
    if measured_range != measurement["value"]:
        raise ValueError("low contrast測定値がgoldと一致しません")
    if measured_range > measurement["fixture_gate_max"]:
        raise ValueError("画像がlow contrast fixture gateを満たしません")
    if measured_range >= clean_dynamic_range:
        raise ValueError("low-quality画像がclean referenceより低コントラストではありません")
    if gold["pages"][0]["source_image_sha256"] != image_entry["sha256"]:
        raise ValueError("goldとlow-quality source imageのSHA-256が一致しません")


def validate_document_content(
    document_path: Path, gold: dict[str, Any], source_image: dict[str, Any]
) -> None:
    page_gold = gold["pages"][0]
    with pymupdf.open(document_path) as document:
        if document.page_count != 1:
            raise ValueError("low-quality fixtureは1 pageである必要があります")
        page = document[0]
        if abs(page.rect.width - page_gold["width_points"]) > 0.01:
            raise ValueError("page幅がgoldと一致しません")
        if abs(page.rect.height - page_gold["height_points"]) > 0.01:
            raise ValueError("page高さがgoldと一致しません")
        if page.rotation != gold["input_characteristics"]["rotation_degrees"]:
            raise ValueError("page回転角がgoldと一致しません")
        if page.get_text().strip():
            raise ValueError("low-quality scan PDFにnative text layerがあります")
        images = page.get_images(full=True)
        expected_size = (source_image["width"], source_image["height"])
        if expected_size not in {(entry[2], entry[3]) for entry in images}:
            raise ValueError("PDF内の画像寸法がsource imageと一致しません")


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

    scan_manifest_path = (
        repository_root
        / "eval/text_pdf_fixtures/manifests/scan_development_manifest.json"
    )
    validate_scan_manifest(scan_manifest_path, repository_root)

    clean_reference = manifest.get("clean_reference")
    if not isinstance(clean_reference, dict):
        raise ValueError("clean_referenceがありません")
    clean_image_entry = clean_reference["source_image"]
    clean_image_path = checked_path(repository_root, clean_image_entry["path"])
    verify_hash(clean_image_path, clean_image_entry["sha256"], "clean_reference.image")
    with Image.open(clean_image_path) as clean_image:
        clean_range = grayscale_dynamic_range(clean_image)
    if clean_range != clean_image_entry["grayscale_dynamic_range"]:
        raise ValueError("clean referenceのdynamic rangeがmanifestと一致しません")
    clean_gold_entry = clean_reference["gold"]
    clean_gold_path = checked_path(repository_root, clean_gold_entry["path"])
    verify_hash(clean_gold_path, clean_gold_entry["sha256"], "clean_reference.gold")
    clean_gold = load_json(clean_gold_path)

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 1:
        raise ValueError("low-quality fixtureは1件である必要があります")
    fixture = fixtures[0]
    if fixture.get("kind") != "low_quality_scanned_text":
        raise ValueError("kindはlow_quality_scanned_textである必要があります")

    document_path = checked_path(repository_root, fixture["document"]["path"])
    verify_hash(document_path, fixture["document"]["sha256"], "document")
    source_image = fixture["source_image"]
    source_image_path = checked_path(repository_root, source_image["path"])
    verify_hash(source_image_path, source_image["sha256"], "source_image")
    rendered = fixture["rendered_page"]
    rendered_path = checked_path(repository_root, rendered["path"])
    verify_hash(rendered_path, rendered["sha256"], "rendered_page")
    gold_path = checked_path(repository_root, fixture["gold"]["path"])
    verify_hash(gold_path, fixture["gold"]["sha256"], "gold")
    gold = load_json(gold_path)

    validate_gold(gold, schema)
    validate_image_quality(source_image_path, source_image, gold, clean_range)
    validate_document_content(document_path, gold, source_image)
    if gold["expected_full_text"] != clean_gold["expected_full_text"]:
        raise ValueError("期待全文がclean fixtureと一致しません")
    if gold["critical_values"] != clean_gold["critical_values"]:
        raise ValueError("重要値がclean fixtureと一致しません")
    if gold["pages"][0]["regions"] != clean_gold["pages"][0]["regions"]:
        raise ValueError("regionがclean fixtureと一致しません")
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
