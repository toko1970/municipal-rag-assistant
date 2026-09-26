"""Validate the public visual holdout protocol without opening sealed content by default."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from eval.validate_visual_fixture import checked_path, load_json, verify_hash


EXPECTED_COUNTS = {
    "visual_type_counts": {
        "process_flow": 4,
        "decision_flow": 4,
        "table": 4,
        "form": 3,
        "timeline": 2,
        "revision_comparison": 3,
    },
    "expected_classification_counts": {
        "grounded": 12,
        "needs_judgment": 4,
        "insufficient_documents": 4,
    },
    "difficulty_counts": {
        "direct": 6,
        "multi_element": 6,
        "boundary_or_revision": 4,
        "paraphrase_or_typo": 4,
    },
}
STATE_ORDER = {
    "PLANNED": 0,
    "SEALED": 1,
    "CANDIDATE_FROZEN": 2,
    "PREDICTIONS_FROZEN": 3,
    "OPENED": 4,
    "CONSUMED": 5,
}


def validate_schema(instance: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: list(error.path),
    )
    if errors:
        messages = [
            f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        ]
        raise ValueError("Schema validationに失敗しました:\n" + "\n".join(messages))


def validate_blueprint(blueprint: dict[str, Any]) -> None:
    if blueprint.get("split") != "sealed_holdout":
        raise ValueError("blueprint splitはsealed_holdoutである必要があります")
    scenario_count = blueprint.get("scenario_count")
    scenario_ids = blueprint.get("scenario_ids")
    if scenario_count != 20 or not isinstance(scenario_ids, list) or len(scenario_ids) != 20:
        raise ValueError("blueprintには20件のscenarioが必要です")
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("scenario IDが重複しています")
    if scenario_ids != [f"VH{index:03d}" for index in range(1, 21)]:
        raise ValueError("scenario IDはVH001からVH020までの順序で固定します")
    for field, expected in EXPECTED_COUNTS.items():
        actual = blueprint.get(field)
        if actual != expected:
            raise ValueError(f"{field}が事前定義した構成と一致しません")
        if sum(actual.values()) != scenario_count:
            raise ValueError(f"{field}の合計がscenario_countと一致しません")
    policy = blueprint.get("document_family_policy", {})
    if policy.get("development_overlap_allowed") is not False:
        raise ValueError("developmentとのdocument family重複は禁止です")
    if policy.get("minimum_distinct_families") != 6:
        raise ValueError("holdoutには最低6つのdocument familyが必要です")


def validate_state_requirements(manifest: dict[str, Any]) -> None:
    stage = STATE_ORDER[manifest["state"]]
    requirements = {
        1: ("questions", "gold"),
        2: ("candidate",),
        3: ("predictions",),
        4: ("opening",),
        5: ("results",),
    }
    for required_stage, fields in requirements.items():
        for field in fields:
            value = manifest[field]
            if stage >= required_stage and value is None:
                raise ValueError(f"{manifest['state']}では{field}が必要です")
            if stage < required_stage and value is not None:
                raise ValueError(f"{manifest['state']}では{field}をまだ設定できません")
    if stage == 0 and manifest["documents"]:
        raise ValueError("PLANNEDではdocumentsをまだ設定できません")
    if stage >= 1:
        families = [document["document_family"] for document in manifest["documents"]]
        document_ids = [document["document_id"] for document in manifest["documents"]]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document IDが重複しています")
        if len(set(families)) < 6:
            raise ValueError("sealed holdoutには6つ以上のdocument familyが必要です")
        kind_counts = Counter(document["kind"] for document in manifest["documents"])
        if any(kind_counts[kind] == 0 for kind in EXPECTED_COUNTS["visual_type_counts"]):
            raise ValueError("sealed documentsには6種類すべての図表が必要です")


def validate_development_family_separation(
    manifest: dict[str, Any], repository_root: Path
) -> None:
    if not manifest["documents"]:
        return
    development = load_json(
        repository_root / "eval/visual_fixtures/manifests/development_manifest.json"
    )
    development_families = {
        fixture["document_family"] for fixture in development["fixtures"]
    }
    holdout_families = {
        document["document_family"] for document in manifest["documents"]
    }
    overlap = development_families & holdout_families
    if overlap:
        raise ValueError(
            f"developmentとsealed holdoutでdocument familyが重複しています: {sorted(overlap)}"
        )


def validate_sealed_artifacts(manifest: dict[str, Any], sealed_root: Path) -> None:
    if STATE_ORDER[manifest["state"]] < STATE_ORDER["SEALED"]:
        raise ValueError("PLANNEDではsealed artifactの照合を実行できません")
    for document in manifest["documents"]:
        path = sealed_root / "documents" / f"{document['document_id']}.pdf"
        if not path.is_file():
            raise ValueError(f"sealed documentが存在しません: {path}")
        verify_hash(path, document["sha256"], document["document_id"])
    gold = manifest["gold"]
    gold_files = {
        "extraction_sha256": sealed_root / "gold/extraction_gold.json",
        "scenario_sha256": sealed_root / "gold/scenario_gold.json",
    }
    for field, path in gold_files.items():
        if not path.is_file():
            raise ValueError(f"sealed goldが存在しません: {path}")
        verify_hash(path, gold[field], field)


def validate_public_manifest(
    manifest_path: Path,
    repository_root: Path,
    sealed_root: Path | None = None,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    schema_entry = manifest.get("manifest_schema")
    if not isinstance(schema_entry, dict):
        raise ValueError("manifest_schemaがありません")
    schema_path = checked_path(repository_root, schema_entry["path"])
    verify_hash(schema_path, schema_entry["sha256"], "manifest_schema")
    schema = load_json(schema_path)
    validate_schema(manifest, schema)
    blueprint_path = checked_path(repository_root, manifest["blueprint"]["path"])
    verify_hash(blueprint_path, manifest["blueprint"]["sha256"], "blueprint")
    validate_blueprint(load_json(blueprint_path))
    questions = manifest["questions"]
    if questions is not None:
        questions_path = checked_path(repository_root, questions["path"])
        verify_hash(questions_path, questions["sha256"], "questions")
    validate_state_requirements(manifest)
    validate_development_family_separation(manifest, repository_root)
    if sealed_root is not None:
        validate_sealed_artifacts(manifest, sealed_root)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--sealed-root", type=Path)
    args = parser.parse_args()
    manifest = validate_public_manifest(
        args.manifest,
        args.repository_root.resolve(),
        args.sealed_root.resolve() if args.sealed_root else None,
    )
    print(
        f"validated holdout={manifest['holdout_id']} state={manifest['state']} "
        f"sealed_content_opened={args.sealed_root is not None}"
    )


if __name__ == "__main__":
    main()
