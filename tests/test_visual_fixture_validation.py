from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eval.validate_visual_fixture import (
    load_json,
    validate_family_separation,
    validate_gold,
    validate_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = load_json(REPOSITORY_ROOT / "design/schemas/visual-extraction-v1.schema.json")
GOLD = load_json(REPOSITORY_ROOT / "eval/visual_fixtures/gold/flowchart_dev_001.json")
MANIFEST_PATH = REPOSITORY_ROOT / "eval/visual_fixtures/manifests/development_manifest.json"


class VisualFixtureValidationTest(unittest.TestCase):
    def test_committed_fixture_is_valid(self):
        manifest = validate_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(manifest["split"], "development")
        self.assertEqual(len(manifest["fixtures"]), 1)

    def test_schema_violation_is_rejected(self):
        gold = deepcopy(GOLD)
        del gold["title"]

        with self.assertRaisesRegex(ValueError, "Schema validation"):
            validate_gold(gold, SCHEMA)

    def test_unknown_edge_node_is_rejected(self):
        gold = deepcopy(GOLD)
        gold["data"]["edges"][0]["to"] = "missing-node"

        with self.assertRaisesRegex(ValueError, "未知のnode"):
            validate_gold(gold, SCHEMA)

    def test_reversed_bbox_is_rejected(self):
        gold = deepcopy(GOLD)
        gold["data"]["nodes"][0]["bbox"]["x1"] = gold["data"]["nodes"][0]["bbox"]["x0"]

        with self.assertRaisesRegex(ValueError, "x0 < x1"):
            validate_gold(gold, SCHEMA)

    def test_manifest_hash_mismatch_is_rejected(self):
        with TemporaryDirectory() as directory:
            temp_root = Path(directory)
            (temp_root / "pyproject.toml").write_text("", encoding="utf-8")
            manifest = load_json(MANIFEST_PATH)
            schema_source = REPOSITORY_ROOT / manifest["schema"]["path"]
            schema_target = temp_root / manifest["schema"]["path"]
            schema_target.parent.mkdir(parents=True)
            schema_target.write_bytes(schema_source.read_bytes())
            manifest["schema"]["sha256"] = "0" * 64
            temp_manifest = temp_root / "manifest.json"
            temp_manifest.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "SHA-256が一致しません: schema"):
                validate_manifest(temp_manifest, temp_root)

    def test_development_holdout_family_overlap_is_rejected(self):
        development = {
            "split": "development",
            "fixtures": [{"document_family": "same-family"}],
        }
        holdout = {
            "split": "sealed_holdout",
            "fixtures": [{"document_family": "same-family"}],
        }

        with self.assertRaisesRegex(ValueError, "document familyが重複"):
            validate_family_separation([development, holdout])


if __name__ == "__main__":
    unittest.main()
