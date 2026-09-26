from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eval.validate_visual_evaluation_set import (
    validate_classification_contract,
    validate_evaluation_set,
    validate_manifest,
)
from eval.validate_visual_fixture import load_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "eval/visual_fixtures/manifests/development_evaluation_manifest.json"
)
EVALUATION_PATH = REPOSITORY_ROOT / "eval/visual_fixtures/development_evaluation_set.json"
SCHEMA_PATH = REPOSITORY_ROOT / "design/schemas/visual-evaluation-set-v1.schema.json"
FIXTURE_MANIFEST_PATH = (
    REPOSITORY_ROOT / "eval/visual_fixtures/manifests/development_manifest.json"
)


class VisualEvaluationSetTest(unittest.TestCase):
    def test_committed_development_set_is_valid(self):
        manifest = validate_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(manifest["evaluation_set"]["scenario_count"], 30)

    def test_each_fixture_has_grounded_judgment_and_insufficient_scenarios(self):
        evaluation_set = load_json(EVALUATION_PATH)
        classifications_by_fixture: dict[str, set[str]] = {}
        for scenario in evaluation_set["scenarios"]:
            fixture_id = scenario["fixture_ids"][0]
            classifications_by_fixture.setdefault(fixture_id, set()).add(
                scenario["expected_classification"]
            )

        self.assertTrue(
            all(
                classifications
                == {"grounded", "needs_judgment", "insufficient_documents"}
                for classifications in classifications_by_fixture.values()
            )
        )

    def test_unknown_gold_element_reference_is_rejected(self):
        evaluation_set = deepcopy(load_json(EVALUATION_PATH))
        evaluation_set["scenarios"][0]["required_evidence"][0]["element_ref"] = (
            "node:missing"
        )

        with self.assertRaisesRegex(ValueError, "未知のelement"):
            validate_evaluation_set(
                evaluation_set,
                load_json(SCHEMA_PATH),
                load_json(FIXTURE_MANIFEST_PATH),
                REPOSITORY_ROOT,
            )

    def test_grounded_without_evidence_is_rejected(self):
        scenario = deepcopy(load_json(EVALUATION_PATH)["scenarios"][0])
        scenario["required_evidence"] = []

        with self.assertRaisesRegex(ValueError, "groundedの契約"):
            validate_classification_contract(scenario)

    def test_judgment_without_missing_condition_is_rejected(self):
        scenario = next(
            scenario
            for scenario in load_json(EVALUATION_PATH)["scenarios"]
            if scenario["expected_classification"] == "needs_judgment"
        )
        scenario = deepcopy(scenario)
        scenario["missing_conditions"] = []

        with self.assertRaisesRegex(ValueError, "needs_judgmentの契約"):
            validate_classification_contract(scenario)

    def test_insufficient_question_cannot_have_gold_evidence(self):
        scenario = next(
            scenario
            for scenario in load_json(EVALUATION_PATH)["scenarios"]
            if scenario["expected_classification"] == "insufficient_documents"
        )
        scenario = deepcopy(scenario)
        scenario["required_evidence"] = [
            {"fixture_id": scenario["fixture_ids"][0], "element_ref": "node:start"}
        ]

        with self.assertRaisesRegex(ValueError, "insufficient_documentsの契約"):
            validate_classification_contract(scenario)

    def test_manifest_hash_mismatch_is_rejected(self):
        with TemporaryDirectory() as directory:
            temp_manifest = Path(directory) / "manifest.json"
            manifest = load_json(MANIFEST_PATH)
            manifest["evaluation_set"]["sha256"] = "0" * 64
            temp_manifest.write_text(
                __import__("json").dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "SHA-256が一致しません: evaluation_set"):
                validate_manifest(temp_manifest, REPOSITORY_ROOT)


if __name__ == "__main__":
    unittest.main()
