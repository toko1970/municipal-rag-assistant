"""Validate visual fixture schema, semantics, files, and split boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

from src.visual_validation import validate_gold


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"JSON objectではありません: {path}")
    return value


def repository_root_for(manifest_path: Path) -> Path:
    for parent in (manifest_path.resolve(), *manifest_path.resolve().parents):
        if (parent / "pyproject.toml").exists():
            return parent
    raise ValueError("repository rootを判定できません。repository_rootを指定してください")


def checked_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"repository外のpathは参照できません: {relative_path}") from error
    if not path.is_file():
        raise ValueError(f"fileが存在しません: {relative_path}")
    return path


def verify_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256が一致しません: {label} / expected={expected} / actual={actual}")


def validate_manifest(manifest_path: Path, repository_root: Path | None = None) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    root = repository_root.resolve() if repository_root else repository_root_for(manifest_path)
    if manifest.get("paths_relative_to") != "repository_root":
        raise ValueError("paths_relative_toはrepository_rootである必要があります")
    if manifest.get("split") not in {"development", "sealed_holdout"}:
        raise ValueError("splitが不正です")

    schema_entry = manifest.get("schema")
    if not isinstance(schema_entry, dict):
        raise ValueError("schema entryがありません")
    schema_path = checked_path(root, schema_entry["path"])
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
        document_path = checked_path(root, fixture["document"]["path"])
        verify_hash(document_path, fixture["document"]["sha256"], f"{fixture_id}.document")
        page_count = len(PdfReader(str(document_path)).pages)

        images_by_page: dict[int, dict[str, Any]] = {}
        for image in fixture.get("source_images", []):
            page = image["page"]
            if page in images_by_page:
                raise ValueError(f"source imageのpageが重複しています: {fixture_id} / {page}")
            image_path = checked_path(root, image["path"])
            verify_hash(image_path, image["sha256"], f"{fixture_id}.source_image[{page}]")
            images_by_page[page] = image

        gold_path = checked_path(root, fixture["gold"]["path"])
        verify_hash(gold_path, fixture["gold"]["sha256"], f"{fixture_id}.gold")
        gold = load_json(gold_path)
        validate_gold(gold, schema)
        if gold["kind"] != fixture["kind"]:
            raise ValueError(f"kindが一致しません: {fixture_id}")
        if gold["page"] < 1 or gold["page"] > page_count:
            raise ValueError(f"goldのpageがPDFの範囲外です: {fixture_id}")
        source_image = images_by_page.get(gold["page"])
        if source_image is None:
            raise ValueError(f"gold pageに対応するsource imageがありません: {fixture_id}")
        if gold["source_image_sha256"] != source_image["sha256"]:
            raise ValueError(f"goldとsource imageのSHA-256が一致しません: {fixture_id}")

    return manifest


def validate_family_separation(manifests: Iterable[dict[str, Any]]) -> None:
    families_by_split: dict[str, set[str]] = {}
    for manifest in manifests:
        split = manifest["split"]
        families = {fixture["document_family"] for fixture in manifest["fixtures"]}
        families_by_split.setdefault(split, set()).update(families)
    overlap = families_by_split.get("development", set()) & families_by_split.get("sealed_holdout", set())
    if overlap:
        raise ValueError(f"developmentとsealed_holdoutでdocument familyが重複しています: {sorted(overlap)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()

    manifests = [validate_manifest(path, args.repository_root) for path in args.manifests]
    validate_family_separation(manifests)
    fixture_count = sum(len(manifest["fixtures"]) for manifest in manifests)
    print(f"validated manifests={len(manifests)} fixtures={fixture_count}")


if __name__ == "__main__":
    main()
