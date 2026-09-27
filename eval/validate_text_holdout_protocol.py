"""Validate the public text holdout protocol without opening sealed content by default."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from eval.validate_large_evaluation_set import load_rows, validate_rows
from eval.validate_visual_fixture import checked_path, load_json, verify_hash
from src.document_loader import parse_markdown_with_metadata


EXPECTED_COUNTS = {
    "variant_counts": {"formal": 50, "paraphrase_or_noisy": 50},
    "expected_classification_counts": {
        "grounded": 30,
        "needs_judgment": 10,
        "insufficient_documents": 10,
    },
    "difficulty_counts": {
        "single_document_direct": 15,
        "multi_document": 15,
        "boundary_or_effective_date": 10,
        "similar_or_absent": 10,
    },
}
EXPECTED_SCENARIO_IDS = [f"TH{index:03d}" for index in range(1, 51)]
EXPECTED_VARIANTS = {"formal", "paraphrase_or_noisy"}
MINIMUM_DOCUMENT_FAMILIES = 5
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
    if blueprint.get("scenario_count") != 50:
        raise ValueError("blueprintには50件のscenarioが必要です")
    if blueprint.get("expression_count") != 100:
        raise ValueError("blueprintには100件の表現が必要です")

    scenario_ids = blueprint.get("scenario_ids")
    if not isinstance(scenario_ids, list) or len(scenario_ids) != 50:
        raise ValueError("blueprintには50件のscenario IDが必要です")
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("scenario IDが重複しています")
    if scenario_ids != EXPECTED_SCENARIO_IDS:
        raise ValueError("scenario IDはTH001からTH050までの順序で固定します")

    for field, expected in EXPECTED_COUNTS.items():
        actual = blueprint.get(field)
        if actual != expected:
            raise ValueError(f"{field}が事前定義した構成と一致しません")
        expected_total = 100 if field == "variant_counts" else 50
        if sum(actual.values()) != expected_total:
            raise ValueError(f"{field}の合計が想定件数と一致しません")

    policy = blueprint.get("document_family_policy", {})
    if policy.get("development_overlap_allowed") is not False:
        raise ValueError("developmentとのdocument family重複は禁止です")
    if policy.get("minimum_distinct_families") != MINIMUM_DOCUMENT_FAMILIES:
        raise ValueError("holdoutには最低5つのdocument familyが必要です")


def validate_public_questions(
    questions: dict[str, Any], holdout_id: str
) -> None:
    expected_top_level = {
        "schema_version",
        "holdout_id",
        "scenario_count",
        "expression_count",
        "scenarios",
    }
    if set(questions) != expected_top_level:
        raise ValueError("公開質問のtop-level fieldが契約と一致しません")
    if questions["schema_version"] != "1.0" or questions["holdout_id"] != holdout_id:
        raise ValueError("公開質問のversionまたはholdout IDが一致しません")
    if questions["scenario_count"] != 50 or questions["expression_count"] != 100:
        raise ValueError("公開質問は50 scenario / 100表現である必要があります")

    scenarios = questions["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) != 50:
        raise ValueError("公開質問には50件のscenarioが必要です")
    if any(not isinstance(scenario, dict) for scenario in scenarios):
        raise ValueError("公開質問のscenarioはobjectである必要があります")
    scenario_ids = [scenario.get("scenario_id") for scenario in scenarios]
    if scenario_ids != EXPECTED_SCENARIO_IDS:
        raise ValueError("公開質問のscenario IDはTH001からTH050の順序で固定します")

    question_texts = []
    for scenario in scenarios:
        if set(scenario) != {"scenario_id", "expressions"}:
            raise ValueError(
                f"公開scenarioに非公開fieldがあります: {scenario.get('scenario_id')}"
            )
        expressions = scenario["expressions"]
        if not isinstance(expressions, list) or len(expressions) != 2:
            raise ValueError(f"各scenarioには2表現が必要です: {scenario['scenario_id']}")
        if any(not isinstance(expression, dict) for expression in expressions):
            raise ValueError(f"表現はobjectである必要があります: {scenario['scenario_id']}")
        variants = []
        for expression in expressions:
            if set(expression) != {"variant_type", "question"}:
                raise ValueError(
                    f"公開表現に非公開fieldがあります: {scenario['scenario_id']}"
                )
            variants.append(expression["variant_type"])
            question = expression["question"]
            if not isinstance(question, str) or not question.strip():
                raise ValueError(f"質問文が空です: {scenario['scenario_id']}")
            question_texts.append(question.strip())
        if set(variants) != EXPECTED_VARIANTS or len(set(variants)) != 2:
            raise ValueError(
                f"formalとparaphrase_or_noisyが1件ずつ必要です: {scenario['scenario_id']}"
            )
    if len(question_texts) != len(set(question_texts)):
        raise ValueError("公開質問文が重複しています")


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
        document_ids = [document["document_id"] for document in manifest["documents"]]
        families = [document["document_family"] for document in manifest["documents"]]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document IDが重複しています")
        if len(set(families)) < MINIMUM_DOCUMENT_FAMILIES:
            raise ValueError("sealed holdoutには5つ以上のdocument familyが必要です")


def validate_development_manifest(
    manifest: dict[str, Any], repository_root: Path
) -> set[str]:
    if manifest.get("split") != "development":
        raise ValueError("text development manifestのsplitがdevelopmentではありません")
    if manifest.get("approved_scenarios") != 100 or manifest.get("questions") != 500:
        raise ValueError("text development setは100 scenario / 500表現である必要があります")

    evaluation_path = checked_path(repository_root, manifest["evaluation_file"])
    verify_hash(evaluation_path, manifest["sha256"], "text development questions")

    row_schema = manifest.get("row_schema")
    if not isinstance(row_schema, dict):
        raise ValueError("text development manifestにrow_schemaがありません")
    row_schema_path = checked_path(repository_root, row_schema["path"])
    verify_hash(row_schema_path, row_schema["sha256"], "text development row schema")
    validate_rows(load_rows(evaluation_path), row_schema=load_json(row_schema_path))

    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("text development manifestにdocumentsがありません")
    document_ids = [document["document_id"] for document in documents]
    families = [document["document_family"] for document in documents]
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("text developmentのdocument IDが重複しています")
    if len(families) != len(set(families)):
        raise ValueError("text developmentのdocument familyが重複しています")
    for document in documents:
        path = checked_path(repository_root, document["path"])
        verify_hash(path, document["sha256"], document["document_id"])
    return set(families)


def validate_development_family_separation(
    manifest: dict[str, Any], development_families: set[str]
) -> None:
    holdout_families = {
        document["document_family"] for document in manifest["documents"]
    }
    overlap = development_families & holdout_families
    if overlap:
        raise ValueError(
            f"developmentとsealed holdoutでdocument familyが重複しています: {sorted(overlap)}"
        )


def validate_gold_semantics(
    gold: dict[str, Any], manifest: dict[str, Any]
) -> None:
    if gold["holdout_id"] != manifest["holdout_id"]:
        raise ValueError("goldのholdout IDがmanifestと一致しません")
    scenarios = gold["scenarios"]
    scenario_ids = [scenario["scenario_id"] for scenario in scenarios]
    if scenario_ids != EXPECTED_SCENARIO_IDS:
        raise ValueError("goldのscenario IDはTH001からTH050の順序で固定します")

    if Counter(scenario["expected_classification"] for scenario in scenarios) != Counter(
        EXPECTED_COUNTS["expected_classification_counts"]
    ):
        raise ValueError("goldの期待分類件数がblueprintと一致しません")
    if Counter(scenario["difficulty"] for scenario in scenarios) != Counter(
        EXPECTED_COUNTS["difficulty_counts"]
    ):
        raise ValueError("goldの難度件数がblueprintと一致しません")

    known_document_ids = {document["document_id"] for document in manifest["documents"]}
    for scenario in scenarios:
        classification = scenario["expected_classification"]
        answerable = scenario["expected_corpus_answerability"]
        document_ids = scenario["expected_document_ids"]
        evidence = scenario["expected_evidence"]
        missing = scenario["missing_conditions"]
        referenced_ids = set(document_ids) | {
            item["document_id"] for item in evidence
        }
        unknown = referenced_ids - known_document_ids
        if unknown:
            raise ValueError(
                f"goldが未知のdocumentを参照しています: {scenario['scenario_id']} / {sorted(unknown)}"
            )
        if any(item["document_id"] not in document_ids for item in evidence):
            raise ValueError(
                f"根拠documentが期待document一覧にありません: {scenario['scenario_id']}"
            )
        if classification == "grounded" and (
            not answerable or not document_ids or not evidence or missing
        ):
            raise ValueError(f"groundedの契約に違反しています: {scenario['scenario_id']}")
        if classification == "needs_judgment" and (
            not answerable or not document_ids or not evidence or not missing
        ):
            raise ValueError(
                f"needs_judgmentの契約に違反しています: {scenario['scenario_id']}"
            )
        if classification == "insufficient_documents" and (
            answerable or document_ids or evidence or missing
        ):
            raise ValueError(
                f"insufficient_documentsの契約に違反しています: {scenario['scenario_id']}"
            )


def validate_sealed_artifacts(
    manifest: dict[str, Any], gold_schema: dict[str, Any], sealed_root: Path
) -> None:
    if STATE_ORDER[manifest["state"]] < STATE_ORDER["SEALED"]:
        raise ValueError("PLANNEDではsealed artifactの照合を実行できません")
    for document in manifest["documents"]:
        path = sealed_root / "documents" / f"{document['document_id']}.md"
        if not path.is_file():
            raise ValueError(f"sealed documentが存在しません: {path}")
        verify_hash(path, document["sha256"], document["document_id"])
        metadata, body = parse_markdown_with_metadata(path)
        if metadata.get("document_id") != document["document_id"]:
            raise ValueError(f"Markdownのdocument_idがmanifestと一致しません: {path}")
        if metadata.get("document_family") != document["document_family"]:
            raise ValueError(f"Markdownのdocument_familyがmanifestと一致しません: {path}")
        if not body.strip():
            raise ValueError(f"sealed documentの本文が空です: {path}")
    gold_path = sealed_root / "gold/scenario_gold.json"
    if not gold_path.is_file():
        raise ValueError(f"sealed goldが存在しません: {gold_path}")
    verify_hash(gold_path, manifest["gold"]["scenario_sha256"], "scenario gold")
    gold = load_json(gold_path)
    validate_schema(gold, gold_schema)
    validate_gold_semantics(gold, manifest)


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

    gold_schema_path = checked_path(repository_root, manifest["gold_schema"]["path"])
    verify_hash(gold_schema_path, manifest["gold_schema"]["sha256"], "gold_schema")
    gold_schema = load_json(gold_schema_path)

    blueprint_path = checked_path(repository_root, manifest["blueprint"]["path"])
    verify_hash(blueprint_path, manifest["blueprint"]["sha256"], "blueprint")
    validate_blueprint(load_json(blueprint_path))

    development_entry = manifest["development_manifest"]
    development_path = checked_path(repository_root, development_entry["path"])
    verify_hash(development_path, development_entry["sha256"], "development_manifest")
    development_families = validate_development_manifest(
        load_json(development_path), repository_root
    )

    questions = manifest["questions"]
    if questions is not None:
        questions_path = checked_path(repository_root, questions["path"])
        verify_hash(questions_path, questions["sha256"], "questions")
        validate_public_questions(load_json(questions_path), manifest["holdout_id"])

    validate_state_requirements(manifest)
    validate_development_family_separation(manifest, development_families)
    if sealed_root is not None:
        validate_sealed_artifacts(manifest, gold_schema, sealed_root)
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
