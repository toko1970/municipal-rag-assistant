from copy import deepcopy
from pathlib import Path
import unittest

from eval.validate_visual_fixture import load_json
from eval.validate_visual_holdout_protocol import (
    validate_blueprint,
    validate_public_manifest,
    validate_state_requirements,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_PATH = REPOSITORY_ROOT / "eval/visual_holdout/scenario_blueprint.json"
MANIFEST_PATH = REPOSITORY_ROOT / "eval/visual_holdout/public_manifest.json"


class VisualHoldoutProtocolTest(unittest.TestCase):
    def test_committed_manifest_is_valid_without_opening_sealed_content(self):
        manifest = validate_public_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(manifest["state"], "SEALED")
        self.assertGreaterEqual(len(manifest["documents"]), 6)
        self.assertEqual(manifest["questions"]["count"], 20)
        for field in ("candidate", "predictions", "opening", "results"):
            self.assertIsNone(manifest[field])

    def test_blueprint_fixes_all_twenty_scenario_ids_and_margins(self):
        blueprint = load_json(BLUEPRINT_PATH)

        validate_blueprint(blueprint)
        self.assertEqual(blueprint["scenario_ids"][0], "VH001")
        self.assertEqual(blueprint["scenario_ids"][-1], "VH020")

    def test_duplicate_scenario_id_is_rejected(self):
        blueprint = deepcopy(load_json(BLUEPRINT_PATH))
        blueprint["scenario_ids"][-1] = blueprint["scenario_ids"][0]

        with self.assertRaisesRegex(ValueError, "scenario IDが重複"):
            validate_blueprint(blueprint)

    def test_sealed_state_without_questions_and_gold_is_rejected(self):
        manifest = deepcopy(load_json(MANIFEST_PATH))
        manifest["state"] = "SEALED"
        manifest["questions"] = None
        manifest["gold"] = None

        with self.assertRaisesRegex(ValueError, "SEALEDではquestionsが必要"):
            validate_state_requirements(manifest)

    def test_planned_state_cannot_claim_frozen_candidate(self):
        manifest = deepcopy(load_json(MANIFEST_PATH))
        manifest["state"] = "PLANNED"
        manifest["questions"] = None
        manifest["gold"] = None
        manifest["documents"] = []
        manifest["candidate"] = {
            "git_commit": "a" * 40,
            "config_manifest_sha256": "b" * 64,
            "frozen_at": "2026-09-26T00:00:00+09:00",
        }

        with self.assertRaisesRegex(ValueError, "PLANNEDではcandidateをまだ設定できません"):
            validate_state_requirements(manifest)

    def test_sealed_directory_is_ignored_by_git(self):
        gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("eval/visual_holdout/.sealed/", gitignore.splitlines())


if __name__ == "__main__":
    unittest.main()
