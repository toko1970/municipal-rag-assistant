from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from eval.validate_text_holdout_protocol import (
    validate_blueprint,
    validate_development_family_separation,
    validate_public_manifest,
    validate_public_questions,
    validate_state_requirements,
)
from eval.validate_visual_fixture import load_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_PATH = REPOSITORY_ROOT / "eval/text_holdout/scenario_blueprint.json"
MANIFEST_PATH = REPOSITORY_ROOT / "eval/text_holdout/public_manifest.json"


def valid_questions() -> dict:
    scenarios = []
    for index in range(1, 51):
        scenario_id = f"TH{index:03d}"
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "expressions": [
                    {
                        "variant_type": "formal",
                        "question": f"正式な質問 {scenario_id}",
                    },
                    {
                        "variant_type": "paraphrase_or_noisy",
                        "question": f"言い換え質問 {scenario_id}",
                    },
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "holdout_id": "text-sealed-holdout-v1",
        "scenario_count": 50,
        "expression_count": 100,
        "scenarios": scenarios,
    }


def planned_manifest() -> dict:
    manifest = deepcopy(load_json(MANIFEST_PATH))
    manifest["state"] = "PLANNED"
    manifest["documents"] = []
    for field in ("questions", "gold", "candidate", "predictions", "opening", "results"):
        manifest[field] = None
    return manifest


class TextHoldoutProtocolTest(unittest.TestCase):
    def test_committed_sealed_manifest_is_valid_without_sealed_access(self):
        with patch(
            "eval.validate_text_holdout_protocol.validate_sealed_artifacts",
            side_effect=AssertionError("Public validation must not open sealed content"),
        ) as sealed_validator:
            manifest = validate_public_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        sealed_validator.assert_not_called()
        self.assertEqual(manifest["state"], "SEALED")
        self.assertGreaterEqual(
            len({document["document_family"] for document in manifest["documents"]}), 5
        )
        self.assertEqual(manifest["questions"]["scenario_count"], 50)
        self.assertEqual(manifest["questions"]["expression_count"], 100)
        self.assertEqual(manifest["gold"]["scenario_count"], 50)
        for field in ("candidate", "predictions", "opening", "results"):
            self.assertIsNone(manifest[field])

    def test_planned_manifest_is_valid_before_artifacts_are_created(self):
        manifest = planned_manifest()
        validate_state_requirements(manifest)

        self.assertEqual(manifest["state"], "PLANNED")
        self.assertEqual(manifest["documents"], [])
        for field in (
            "questions",
            "gold",
            "candidate",
            "predictions",
            "opening",
            "results",
        ):
            self.assertIsNone(manifest[field])

    def test_blueprint_fixes_fifty_scenarios_and_one_hundred_expressions(self):
        blueprint = load_json(BLUEPRINT_PATH)

        validate_blueprint(blueprint)
        self.assertEqual(blueprint["scenario_ids"][0], "TH001")
        self.assertEqual(blueprint["scenario_ids"][-1], "TH050")
        self.assertEqual(sum(blueprint["variant_counts"].values()), 100)

    def test_duplicate_blueprint_scenario_id_is_rejected(self):
        blueprint = deepcopy(load_json(BLUEPRINT_PATH))
        blueprint["scenario_ids"][-1] = blueprint["scenario_ids"][0]

        with self.assertRaisesRegex(ValueError, "scenario IDが重複"):
            validate_blueprint(blueprint)

    def test_each_public_scenario_requires_both_variants(self):
        questions = valid_questions()
        questions["scenarios"][0]["expressions"][1]["variant_type"] = "formal"

        with self.assertRaisesRegex(ValueError, "formalとparaphrase_or_noisy"):
            validate_public_questions(questions, "text-sealed-holdout-v1")

    def test_public_questions_reject_gold_fields(self):
        questions = valid_questions()
        questions["scenarios"][0]["expected_classification"] = "grounded"

        with self.assertRaisesRegex(ValueError, "非公開field"):
            validate_public_questions(questions, "text-sealed-holdout-v1")

    def test_sealed_state_without_questions_and_gold_is_rejected(self):
        manifest = planned_manifest()
        manifest["state"] = "SEALED"

        with self.assertRaisesRegex(ValueError, "SEALEDではquestionsが必要"):
            validate_state_requirements(manifest)

    def test_planned_state_cannot_claim_frozen_candidate(self):
        manifest = planned_manifest()
        manifest["candidate"] = {
            "git_commit": "a" * 40,
            "config_manifest_sha256": "b" * 64,
            "frozen_at": "2026-09-27T00:00:00+09:00",
        }

        with self.assertRaisesRegex(ValueError, "PLANNEDではcandidateをまだ設定できません"):
            validate_state_requirements(manifest)

    def test_development_family_overlap_is_rejected(self):
        manifest = deepcopy(load_json(MANIFEST_PATH))
        manifest["documents"] = [
            {
                "document_id": "HOLDOUT-001",
                "document_family": "salary_rules",
                "format": "markdown",
                "sha256": "a" * 64,
            }
        ]

        with self.assertRaisesRegex(ValueError, "document familyが重複"):
            validate_development_family_separation(manifest, {"salary_rules"})

    def test_text_sealed_directory_is_ignored_by_git(self):
        gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("eval/text_holdout/.sealed/", gitignore.splitlines())


if __name__ == "__main__":
    unittest.main()
