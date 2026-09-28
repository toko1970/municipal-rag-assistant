"""Validate the public visual holdout protocol without opening sealed content by default."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from eval.validate_visual_fixture import checked_path, load_json, verify_hash
from src.visual_ingestion import load_visual_schema
from src.visual_validation import validate_gold


LEGACY_EXPECTED_COUNTS = {
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
CANDIDATE_CONFIG_PATH = "eval/visual_holdout/candidate_config.json"
PREDICTIONS_ROOT = "eval/results"


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
    if not isinstance(scenario_count, int) or scenario_count < 1:
        raise ValueError("blueprintのscenario_countは1以上の整数が必要です")
    if not isinstance(scenario_ids, list) or len(scenario_ids) != scenario_count:
        raise ValueError("blueprintのscenario ID件数がscenario_countと一致しません")
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("scenario IDが重複しています")
    for field in (
        "visual_type_counts",
        "expected_classification_counts",
        "difficulty_counts",
    ):
        actual = blueprint.get(field)
        if not isinstance(actual, dict) or not actual:
            raise ValueError(f"{field}には事前定義した件数が必要です")
        if any(not isinstance(value, int) or value < 0 for value in actual.values()):
            raise ValueError(f"{field}の件数は0以上の整数である必要があります")
        if sum(actual.values()) != scenario_count:
            raise ValueError(f"{field}の合計がscenario_countと一致しません")
    policy = blueprint.get("document_family_policy", {})
    if policy.get("development_overlap_allowed") is not False:
        raise ValueError("developmentとのdocument family重複は禁止です")
    minimum_families = policy.get("minimum_distinct_families")
    if not isinstance(minimum_families, int) or minimum_families < 1:
        raise ValueError("minimum_distinct_familiesは1以上の整数が必要です")


def validate_state_requirements(
    manifest: dict[str, Any], blueprint: dict[str, Any] | None = None
) -> None:
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
        blueprint = blueprint or {
            **LEGACY_EXPECTED_COUNTS,
            "scenario_count": 20,
            "document_family_policy": {"minimum_distinct_families": 6},
        }
        scenario_count = blueprint["scenario_count"]
        if manifest["questions"]["count"] != scenario_count:
            raise ValueError("questions件数がblueprintと一致しません")
        if manifest["gold"]["scenario_count"] != scenario_count:
            raise ValueError("gold件数がblueprintと一致しません")
        families = [document["document_family"] for document in manifest["documents"]]
        document_ids = [document["document_id"] for document in manifest["documents"]]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document IDが重複しています")
        minimum_families = blueprint["document_family_policy"][
            "minimum_distinct_families"
        ]
        if len(set(families)) < minimum_families:
            raise ValueError(
                f"sealed holdoutには{minimum_families}つ以上のdocument familyが必要です"
            )
        kind_counts = Counter(document["kind"] for document in manifest["documents"])
        required_kinds = {
            kind for kind, count in blueprint["visual_type_counts"].items() if count > 0
        }
        if any(kind_counts[kind] == 0 for kind in required_kinds):
            raise ValueError(
                "sealed documentsにblueprint対象の図表種類が不足しています"
            )


def candidate_config_path(manifest: dict[str, Any], repository_root: Path) -> Path:
    """Resolve the candidate config next to the holdout blueprint."""

    holdout_dir = Path(manifest["blueprint"]["path"]).parent
    return checked_path(repository_root, str(holdout_dir / "candidate_config.json"))


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


def validate_candidate_artifact(
    manifest: dict[str, Any], repository_root: Path
) -> None:
    """Verify the frozen candidate without inspecting sealed documents or gold."""

    if STATE_ORDER[manifest["state"]] < STATE_ORDER["CANDIDATE_FROZEN"]:
        return
    candidate = manifest["candidate"]
    config_path = candidate_config_path(manifest, repository_root)
    verify_hash(
        config_path,
        candidate["config_manifest_sha256"],
        "candidate_config",
    )
    config = load_json(config_path)
    if config.get("holdout_id") != manifest["holdout_id"]:
        raise ValueError("candidate configのholdout_idが一致しません")
    if config.get("source_git_commit") != candidate["git_commit"]:
        raise ValueError("candidate configのGit commitが一致しません")
    if config.get("frozen_at") != candidate["frozen_at"]:
        raise ValueError("candidate configのfrozen_atが一致しません")
    if config.get("selection_split") != "development":
        raise ValueError("candidateはdevelopment splitだけで選定する必要があります")
    if config.get("sealed_holdout_accessed") is not False:
        raise ValueError("候補固定時点でsealed holdoutへアクセスしてはいけません")
    policy = config.get("execution_policy", {})
    if policy.get("retry_count") != 0:
        raise ValueError("holdout実行のretry_countは0で固定する必要があります")
    if policy.get("gold_available_to_runner") is not False:
        raise ValueError("prediction runnerからgoldを参照できない設定が必要です")
    for evidence in config.get("development_evidence", []):
        path = checked_path(repository_root, evidence["path"])
        verify_hash(
            path, evidence["sha256"], f"development_evidence:{evidence['path']}"
        )


def validate_prediction_artifact(
    manifest: dict[str, Any], repository_root: Path
) -> None:
    if STATE_ORDER[manifest["state"]] < STATE_ORDER["PREDICTIONS_FROZEN"]:
        return
    predictions = manifest["predictions"]
    path = checked_path(
        repository_root,
        f"{PREDICTIONS_ROOT}/{predictions['run_id']}/predictions.json",
    )
    verify_hash(path, predictions["sha256"], "predictions")
    bundle = load_json(path)
    outcomes = bundle.get("predictions")
    if not isinstance(outcomes, list) or len(outcomes) != predictions["attempt_count"]:
        raise ValueError("prediction outcome件数がpublic manifestと一致しません")
    if bundle.get("summary", {}).get("sealed_gold_accessed") is not False:
        raise ValueError("prediction固定前にgoldへアクセスしてはいけません")


def validate_result_artifact(manifest: dict[str, Any], repository_root: Path) -> None:
    if STATE_ORDER[manifest["state"]] < STATE_ORDER["CONSUMED"]:
        return
    results = manifest["results"]
    path = checked_path(repository_root, results["path"])
    verify_hash(path, results["sha256"], "results")
    score = load_json(path)
    if score.get("holdout_id") != manifest["holdout_id"]:
        raise ValueError("scoreのholdout_idがpublic manifestと一致しません")
    if score.get("holdout_reusable_as_unseen") is not False:
        raise ValueError("consumed holdoutを未見評価として再利用できません")


def validate_sealed_artifacts(
    manifest: dict[str, Any],
    sealed_root: Path,
    repository_root: Path,
    blueprint: dict[str, Any],
) -> None:
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
    extraction_gold = load_json(gold_files["extraction_sha256"])
    visual_schema = load_visual_schema()
    document_ids = {document["document_id"] for document in manifest["documents"]}
    extraction_ids = set()
    for item in extraction_gold.get("documents", []):
        extraction_ids.add(item["document_id"])
        validate_gold(item["annotation"], visual_schema)
    if extraction_ids != document_ids:
        raise ValueError("extraction goldのdocument IDがpublic manifestと一致しません")

    scenario_gold = load_json(gold_files["scenario_sha256"])
    if manifest["schema_version"] == "2.0":
        scenario_schema = load_json(
            repository_root
            / "design/schemas/visual-holdout-scenario-gold-v2.schema.json"
        )
        validate_schema(scenario_gold, scenario_schema)
    scenarios = scenario_gold.get("scenarios", [])
    if scenario_gold.get("scenario_count") != blueprint["scenario_count"]:
        raise ValueError("scenario gold件数がblueprintと一致しません")
    if [item.get("scenario_id") for item in scenarios] != blueprint["scenario_ids"]:
        raise ValueError("scenario goldのIDまたは順序がblueprintと一致しません")
    for field, scenario_field in (
        ("visual_type_counts", "visual_type"),
        ("expected_classification_counts", "expected_classification"),
        ("difficulty_counts", "difficulty"),
    ):
        if Counter(item[scenario_field] for item in scenarios) != Counter(
            blueprint[field]
        ):
            raise ValueError(
                f"scenario goldの{scenario_field}件数がblueprintと一致しません"
            )
    for scenario in scenarios:
        required_documents = set(scenario.get("required_document_ids", []))
        if not required_documents.issubset(document_ids):
            raise ValueError("scenario goldが未知のdocument IDを参照しています")
        classification = scenario["expected_classification"]
        answerable = scenario.get("expected_corpus_answerability")
        evidence = scenario.get("required_evidence", [])
        missing = scenario.get("missing_conditions", [])
        if classification == "grounded" and (not answerable or not evidence or missing):
            raise ValueError("grounded goldのanswerability/evidence条件が不正です")
        if classification == "needs_judgment" and (
            not answerable or not evidence or not missing
        ):
            raise ValueError("needs_judgment goldの条件が不正です")
        if classification == "insufficient_documents" and (
            answerable or required_documents or evidence
        ):
            raise ValueError("insufficient_documents goldの条件が不正です")


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
    blueprint = load_json(blueprint_path)
    validate_blueprint(blueprint)
    questions = manifest["questions"]
    if questions is not None:
        questions_path = checked_path(repository_root, questions["path"])
        verify_hash(questions_path, questions["sha256"], "questions")
        question_set = load_json(questions_path)
        if question_set.get("scenario_count") != blueprint["scenario_count"]:
            raise ValueError("公開質問のscenario_countがblueprintと一致しません")
        question_ids = [
            item.get("scenario_id") for item in question_set.get("scenarios", [])
        ]
        if question_ids != blueprint["scenario_ids"]:
            raise ValueError("公開質問のscenario IDまたは順序がblueprintと一致しません")
    validate_state_requirements(manifest, blueprint)
    validate_development_family_separation(manifest, repository_root)
    validate_candidate_artifact(manifest, repository_root)
    validate_prediction_artifact(manifest, repository_root)
    validate_result_artifact(manifest, repository_root)
    if sealed_root is not None:
        validate_sealed_artifacts(manifest, sealed_root, repository_root, blueprint)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
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
