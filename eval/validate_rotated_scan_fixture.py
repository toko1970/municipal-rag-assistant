"""Validate PDF rotation fixtures and their upright normalization contract."""

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


def validate_source_contract(
    source_fixture: dict[str, Any], repository_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    scan_manifest_path = (
        repository_root
        / "eval/text_pdf_fixtures/manifests/scan_development_manifest.json"
    )
    validate_scan_manifest(scan_manifest_path, repository_root)

    source_image = source_fixture["source_image"]
    source_image_path = checked_path(repository_root, source_image["path"])
    verify_hash(source_image_path, source_image["sha256"], "source_fixture.image")
    with Image.open(source_image_path) as image:
        if image.size != (source_image["width"], source_image["height"]):
            raise ValueError("source fixture画像寸法がmanifestと一致しません")
        dpi = image.info.get("dpi")
        if dpi is None or any(abs(value - source_image["dpi"]) > 0.1 for value in dpi):
            raise ValueError("source fixtureのdpiがmanifestと一致しません")

    reference = source_fixture["upright_reference_page"]
    reference_path = checked_path(repository_root, reference["path"])
    verify_hash(reference_path, reference["sha256"], "source_fixture.reference")

    source_gold_entry = source_fixture["gold"]
    source_gold_path = checked_path(repository_root, source_gold_entry["path"])
    verify_hash(source_gold_path, source_gold_entry["sha256"], "source_fixture.gold")
    return source_image, load_json(source_gold_path)


def validate_document_content(
    document_path: Path,
    gold: dict[str, Any],
    source_image: dict[str, Any],
) -> None:
    page_gold = gold["pages"][0]
    expected_rotation = gold["input_characteristics"]["rotation_degrees"]
    with pymupdf.open(document_path) as document:
        if document.page_count != 1:
            raise ValueError("回転fixtureは1 pageである必要があります")
        page = document[0]
        if page.rotation != expected_rotation:
            raise ValueError("PDF rotationがgoldと一致しません")
        if abs(page.mediabox.width - page_gold["media_width_points"]) > 0.01:
            raise ValueError("media box幅がgoldと一致しません")
        if abs(page.mediabox.height - page_gold["media_height_points"]) > 0.01:
            raise ValueError("media box高さがgoldと一致しません")
        if abs(page.rect.width - page_gold["displayed_width_points"]) > 0.01:
            raise ValueError("表示時のpage幅がgoldと一致しません")
        if abs(page.rect.height - page_gold["displayed_height_points"]) > 0.01:
            raise ValueError("表示時のpage高さがgoldと一致しません")
        if page.get_text().strip():
            raise ValueError("回転scan PDFにnative text layerがあります")
        images = page.get_images(full=True)
        expected_size = (source_image["width"], source_image["height"])
        if expected_size not in {(entry[2], entry[3]) for entry in images}:
            raise ValueError("PDF内の画像寸法がsource imageと一致しません")


def validate_page_images(
    fixture: dict[str, Any],
    gold: dict[str, Any],
    source_fixture: dict[str, Any],
    repository_root: Path,
) -> None:
    for key in ("raw_rendered_page", "normalized_page"):
        entry = fixture[key]
        path = checked_path(repository_root, entry["path"])
        verify_hash(path, entry["sha256"], f"{fixture['fixture_id']}.{key}")
        with Image.open(path) as image:
            if image.size != (entry["width"], entry["height"]):
                raise ValueError(f"{key}の画像寸法がmanifestと一致しません")

    normalized = fixture["normalized_page"]
    reference = source_fixture["upright_reference_page"]
    expected_hash = gold["pages"][0]["expected_normalized_image_sha256"]
    if normalized["sha256"] != reference["sha256"]:
        raise ValueError("正規化画像が正立reference画像と一致しません")
    if normalized["sha256"] != expected_hash:
        raise ValueError("正規化画像がgoldの期待hashと一致しません")

    angle = gold["input_characteristics"]["rotation_degrees"]
    raw = fixture["raw_rendered_page"]
    if angle in (90, 270) and raw["width"] <= raw["height"]:
        raise ValueError("90/270度の表示画像は横長である必要があります")
    if angle == 180 and raw["width"] >= raw["height"]:
        raise ValueError("180度の表示画像は縦長である必要があります")


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

    source_fixture = manifest.get("source_fixture")
    if not isinstance(source_fixture, dict):
        raise ValueError("source_fixtureがありません")
    source_image, source_gold = validate_source_contract(
        source_fixture, repository_root
    )

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("fixturesが空です")
    angles = [fixture.get("rotation_degrees") for fixture in fixtures]
    if angles != [90, 180, 270]:
        raise ValueError("rotation fixtureは90/180/270度の順で必要です")
    fixture_ids = [fixture.get("fixture_id") for fixture in fixtures]
    if any(not value for value in fixture_ids) or len(fixture_ids) != len(
        set(fixture_ids)
    ):
        raise ValueError("fixture_idは空でない一意な値である必要があります")

    for fixture in fixtures:
        fixture_id = fixture["fixture_id"]
        if fixture["kind"] != "rotated_scanned_text":
            raise ValueError(f"kindが不正です: {fixture_id}")
        document_path = checked_path(repository_root, fixture["document"]["path"])
        verify_hash(document_path, fixture["document"]["sha256"], fixture_id)
        gold_path = checked_path(repository_root, fixture["gold"]["path"])
        verify_hash(gold_path, fixture["gold"]["sha256"], f"{fixture_id}.gold")
        gold = load_json(gold_path)
        validate_gold(gold, schema)
        if gold["input_characteristics"]["rotation_degrees"] != fixture[
            "rotation_degrees"
        ]:
            raise ValueError(f"manifestとgoldのrotationが一致しません: {fixture_id}")
        if gold["expected_full_text"] != source_gold["expected_full_text"]:
            raise ValueError(f"期待全文がsource fixtureと一致しません: {fixture_id}")
        if gold["critical_values"] != source_gold["critical_values"]:
            raise ValueError(f"重要値がsource fixtureと一致しません: {fixture_id}")
        if gold["pages"][0]["source_image_sha256"] != source_image["sha256"]:
            raise ValueError(f"source image hashがgoldと一致しません: {fixture_id}")
        if gold["pages"][0]["regions"] != source_gold["pages"][0]["regions"]:
            raise ValueError(f"正立regionがsource fixtureと一致しません: {fixture_id}")
        validate_document_content(document_path, gold, source_image)
        validate_page_images(fixture, gold, source_fixture, repository_root)
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
