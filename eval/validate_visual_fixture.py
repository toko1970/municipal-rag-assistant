"""Validate visual fixture schema, semantics, files, and split boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator
from pypdf import PdfReader


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


def validate_bbox(bbox: dict[str, Any], location: str) -> None:
    if bbox["x0"] >= bbox["x1"]:
        raise ValueError(f"bboxはx0 < x1である必要があります: {location}")
    if bbox["y0"] >= bbox["y1"]:
        raise ValueError(f"bboxはy0 < y1である必要があります: {location}")


def iter_bboxes(value: Any, location: str = "$") -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        if set(("x0", "y0", "x1", "y1")).issubset(value):
            yield location, value
        for key, child in value.items():
            yield from iter_bboxes(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_bboxes(child, f"{location}[{index}]")


def validate_gold(gold: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(gold), key=lambda error: list(error.path))
    if errors:
        messages = [
            f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        ]
        raise ValueError("Schema validationに失敗しました:\n" + "\n".join(messages))

    for location, bbox in iter_bboxes(gold):
        validate_bbox(bbox, location)

    if gold["kind"] == "flowchart":
        validate_flowchart(gold["data"])


def validate_flowchart(flowchart: dict[str, Any]) -> None:
    nodes = flowchart["nodes"]
    edges = flowchart["edges"]
    node_ids = [node["id"] for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("flowchartのnode IDが重複しています")
    known_ids = set(node_ids)
    node_by_id = {node["id"]: node for node in nodes}
    start_ids = [node["id"] for node in nodes if node["node_type"] == "start"]
    end_ids = {node["id"] for node in nodes if node["node_type"] == "end"}
    if len(start_ids) != 1:
        raise ValueError("flowchartにはstart nodeが1件必要です")
    if not end_ids:
        raise ValueError("flowchartにはend nodeが1件以上必要です")

    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in node_ids}
    incoming_count = {node_id: 0 for node_id in node_ids}
    for index, edge in enumerate(edges):
        if edge["from"] not in known_ids:
            raise ValueError(f"edge[{index}].fromが未知のnodeを参照しています: {edge['from']}")
        if edge["to"] not in known_ids:
            raise ValueError(f"edge[{index}].toが未知のnodeを参照しています: {edge['to']}")
        outgoing[edge["from"]].append(edge)
        incoming_count[edge["to"]] += 1

    start_id = start_ids[0]
    if incoming_count[start_id] != 0:
        raise ValueError("start nodeにはincoming edgeを設定できません")
    for end_id in end_ids:
        if outgoing[end_id]:
            raise ValueError(f"end nodeにはoutgoing edgeを設定できません: {end_id}")
    for node_id, node in node_by_id.items():
        if node["node_type"] != "decision":
            continue
        decision_edges = outgoing[node_id]
        if len(decision_edges) < 2:
            raise ValueError(f"decision nodeには2件以上のoutgoing edgeが必要です: {node_id}")
        conditions = [edge["condition"] for edge in decision_edges]
        if any(not condition or not condition.strip() for condition in conditions):
            raise ValueError(f"decision nodeの分岐条件は空にできません: {node_id}")
        if len(conditions) != len(set(conditions)):
            raise ValueError(f"decision nodeの分岐条件が重複しています: {node_id}")

    reachable = {start_id}
    pending = [start_id]
    while pending:
        current = pending.pop()
        for edge in outgoing[current]:
            if edge["to"] not in reachable:
                reachable.add(edge["to"])
                pending.append(edge["to"])
    unreachable = known_ids - reachable
    if unreachable:
        raise ValueError(f"start nodeから到達できないnodeがあります: {sorted(unreachable)}")


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
