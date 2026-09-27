"""Validate visual RAG evaluation scenarios and their gold element references."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from eval.validate_visual_fixture import checked_path, load_json, verify_hash


EXPECTED_CLASSIFICATIONS = {
    "grounded": 18,
    "needs_judgment": 6,
    "insufficient_documents": 6,
}
EXPECTED_VISUAL_TYPES = {
    "process_flow": 5,
    "decision_flow": 5,
    "timeline": 5,
    "table": 5,
    "form": 5,
    "revision_comparison": 5,
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


def element_refs(gold: dict[str, Any]) -> set[str]:
    data = gold["data"]
    if gold["kind"] == "flowchart":
        refs = {f"node:{node['id']}" for node in data["nodes"]}
        refs.update(f"edge:{edge['from']}->{edge['to']}" for edge in data["edges"])
        return refs
    if gold["kind"] == "table":
        return {f"cell:r{cell['row']}c{cell['column']}" for cell in data["cells"]}
    if gold["kind"] == "form":
        return {f"field:{field['id']}" for field in data["fields"]}
    if gold["kind"] == "timeline":
        return {f"event:{event['id']}" for event in data["events"]}
    raise ValueError(f"未対応のgold kindです: {gold['kind']}")


def validate_classification_contract(scenario: dict[str, Any]) -> None:
    classification = scenario["expected_classification"]
    evidence = scenario["required_evidence"]
    missing = scenario["missing_conditions"]
    answerable = scenario["expected_corpus_answerability"]
    if classification == "grounded" and (not answerable or not evidence or missing):
        raise ValueError(f"groundedの契約に違反しています: {scenario['scenario_id']}")
    if classification == "needs_judgment" and (
        not answerable or not evidence or not missing
    ):
        raise ValueError(f"needs_judgmentの契約に違反しています: {scenario['scenario_id']}")
    if classification == "insufficient_documents" and (answerable or evidence or missing):
        raise ValueError(
            f"insufficient_documentsの契約に違反しています: {scenario['scenario_id']}"
        )


def validate_evaluation_set(
    evaluation_set: dict[str, Any],
    schema: dict[str, Any],
    fixture_manifest: dict[str, Any],
    repository_root: Path,
) -> None:
    validate_schema(evaluation_set, schema)
    if evaluation_set["split"] != "development":
        raise ValueError("このvalidatorの対象splitはdevelopmentです")
    scenarios = evaluation_set["scenarios"]
    if evaluation_set["scenario_count"] != len(scenarios) or len(scenarios) != 30:
        raise ValueError("development evaluation setには30 scenarioが必要です")
    scenario_ids = [scenario["scenario_id"] for scenario in scenarios]
    if scenario_ids != [f"VD{index:03d}" for index in range(1, 31)]:
        raise ValueError("scenario IDはVD001からVD030までの順序で固定します")

    fixtures = {fixture["fixture_id"]: fixture for fixture in fixture_manifest["fixtures"]}
    known_refs: dict[str, set[str]] = {}
    for fixture_id, fixture in fixtures.items():
        gold = load_json(checked_path(repository_root, fixture["gold"]["path"]))
        known_refs[fixture_id] = element_refs(gold)

    for scenario in scenarios:
        validate_classification_contract(scenario)
        for fixture_id in scenario["fixture_ids"]:
            if fixture_id not in fixtures:
                raise ValueError(
                    f"未知のfixtureを参照しています: {scenario['scenario_id']} / {fixture_id}"
                )
        for evidence in scenario["required_evidence"]:
            fixture_id = evidence["fixture_id"]
            element_ref = evidence["element_ref"]
            if fixture_id not in scenario["fixture_ids"]:
                raise ValueError(
                    f"evidenceのfixtureがfixture_idsにありません: {scenario['scenario_id']}"
                )
            if element_ref not in known_refs[fixture_id]:
                raise ValueError(
                    f"未知のelementを参照しています: {scenario['scenario_id']} / "
                    f"{fixture_id} / {element_ref}"
                )

    classifications = Counter(
        scenario["expected_classification"] for scenario in scenarios
    )
    if dict(classifications) != EXPECTED_CLASSIFICATIONS:
        raise ValueError("期待分類の配分が18/6/6と一致しません")
    visual_types = Counter(scenario["visual_type"] for scenario in scenarios)
    if dict(visual_types) != EXPECTED_VISUAL_TYPES:
        raise ValueError("各図表種類のscenarioは5件ずつ必要です")
    fixture_counts = Counter(
        fixture_id for scenario in scenarios for fixture_id in scenario["fixture_ids"]
    )
    if set(fixture_counts) != set(fixtures) or any(count != 5 for count in fixture_counts.values()):
        raise ValueError("各fixtureは5 scenarioで評価する必要があります")


def validate_manifest(manifest_path: Path, repository_root: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    for field in ("schema", "fixture_manifest", "evaluation_set"):
        entry = manifest[field]
        path = checked_path(repository_root, entry["path"])
        verify_hash(path, entry["sha256"], field)
    schema = load_json(repository_root / manifest["schema"]["path"])
    fixture_manifest = load_json(repository_root / manifest["fixture_manifest"]["path"])
    evaluation_set = load_json(repository_root / manifest["evaluation_set"]["path"])
    validate_evaluation_set(evaluation_set, schema, fixture_manifest, repository_root)
    if manifest["evaluation_set"]["scenario_count"] != evaluation_set["scenario_count"]:
        raise ValueError("manifestとevaluation setのscenario_countが一致しません")
    if manifest.get("review_status") != evaluation_set["review_status"]:
        raise ValueError("manifestとevaluation setのreview_statusが一致しません")
    count_fields = {
        "classification_counts": "expected_classification",
        "visual_type_counts": "visual_type",
        "difficulty_counts": "difficulty",
    }
    for manifest_field, scenario_field in count_fields.items():
        actual = dict(Counter(row[scenario_field] for row in evaluation_set["scenarios"]))
        if manifest.get(manifest_field) != actual:
            raise ValueError(f"manifestの{manifest_field}がevaluation setと一致しません")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    manifest = validate_manifest(args.manifest, args.repository_root.resolve())
    print(
        f"validated dataset={manifest['dataset_version']} "
        f"scenarios={manifest['evaluation_set']['scenario_count']}"
    )


if __name__ == "__main__":
    main()
