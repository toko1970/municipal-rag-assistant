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
ELIGIBILITY_GOLD = load_json(REPOSITORY_ROOT / "eval/visual_fixtures/gold/flowchart_dev_002.json")
TIMELINE_GOLD = load_json(REPOSITORY_ROOT / "eval/visual_fixtures/gold/timeline_dev_001.json")
AMOUNT_TABLE_GOLD = load_json(REPOSITORY_ROOT / "eval/visual_fixtures/gold/table_dev_001.json")
FORM_GOLD = load_json(REPOSITORY_ROOT / "eval/visual_fixtures/gold/form_dev_001.json")
REVISION_TABLE_GOLD = load_json(REPOSITORY_ROOT / "eval/visual_fixtures/gold/table_dev_002.json")
MANIFEST_PATH = REPOSITORY_ROOT / "eval/visual_fixtures/manifests/development_manifest.json"


class VisualFixtureValidationTest(unittest.TestCase):
    def test_committed_fixture_is_valid(self):
        manifest = validate_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(manifest["split"], "development")
        self.assertEqual(len(manifest["fixtures"]), 6)

    def test_eligibility_flowchart_has_multiple_decisions_and_outcomes(self):
        validate_gold(ELIGIBILITY_GOLD, SCHEMA)

        nodes = ELIGIBILITY_GOLD["data"]["nodes"]
        self.assertEqual(sum(node["node_type"] == "decision" for node in nodes), 3)
        self.assertEqual(sum(node["node_type"] == "end" for node in nodes), 3)

    def test_timeline_preserves_five_ordered_events(self):
        validate_gold(TIMELINE_GOLD, SCHEMA)

        event_ids = [event["id"] for event in TIMELINE_GOLD["data"]["events"]]
        self.assertEqual(
            event_ids,
            ["change_known", "submit", "review", "register", "payment"],
        )

    def test_duplicate_timeline_event_id_is_rejected(self):
        gold = deepcopy(TIMELINE_GOLD)
        gold["data"]["events"][1]["id"] = gold["data"]["events"][0]["id"]

        with self.assertRaisesRegex(ValueError, "event IDが重複"):
            validate_gold(gold, SCHEMA)

    def test_timeline_with_one_event_is_rejected(self):
        gold = deepcopy(TIMELINE_GOLD)
        gold["data"]["events"] = gold["data"]["events"][:1]

        with self.assertRaisesRegex(ValueError, "eventが2件以上"):
            validate_gold(gold, SCHEMA)

    def test_amount_table_contains_a_row_span(self):
        validate_gold(AMOUNT_TABLE_GOLD, SCHEMA)

        self.assertTrue(
            any(cell["row_span"] == 2 for cell in AMOUNT_TABLE_GOLD["data"]["cells"])
        )

    def test_revision_table_contains_column_spans(self):
        validate_gold(REVISION_TABLE_GOLD, SCHEMA)

        self.assertTrue(
            any(cell["column_span"] > 1 for cell in REVISION_TABLE_GOLD["data"]["cells"])
        )

    def test_out_of_range_table_cell_is_rejected(self):
        gold = deepcopy(AMOUNT_TABLE_GOLD)
        gold["data"]["cells"][0]["row_span"] = gold["data"]["row_count"] + 1

        with self.assertRaisesRegex(ValueError, "行列範囲を超えています"):
            validate_gold(gold, SCHEMA)

    def test_overlapping_table_cell_is_rejected(self):
        gold = deepcopy(AMOUNT_TABLE_GOLD)
        duplicate = deepcopy(gold["data"]["cells"][0])
        duplicate["text"] = "重複cell"
        gold["data"]["cells"].append(duplicate)

        with self.assertRaisesRegex(ValueError, "table cellが重複"):
            validate_gold(gold, SCHEMA)

    def test_table_without_cells_is_rejected(self):
        gold = deepcopy(AMOUNT_TABLE_GOLD)
        gold["data"]["cells"] = []

        with self.assertRaisesRegex(ValueError, "cellが1件以上"):
            validate_gold(gold, SCHEMA)

    def test_form_preserves_expected_field_order(self):
        validate_gold(FORM_GOLD, SCHEMA)

        field_ids = [field["id"] for field in FORM_GOLD["data"]["fields"]]
        self.assertEqual(field_ids[0], "employee_id")
        self.assertEqual(field_ids[-1], "attachment")

    def test_duplicate_form_field_id_is_rejected(self):
        gold = deepcopy(FORM_GOLD)
        gold["data"]["fields"][1]["id"] = gold["data"]["fields"][0]["id"]

        with self.assertRaisesRegex(ValueError, "field IDが重複"):
            validate_gold(gold, SCHEMA)

    def test_form_without_fields_is_rejected(self):
        gold = deepcopy(FORM_GOLD)
        gold["data"]["fields"] = []

        with self.assertRaisesRegex(ValueError, "fieldが1件以上"):
            validate_gold(gold, SCHEMA)

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

    def test_unreachable_node_is_rejected(self):
        gold = deepcopy(GOLD)
        gold["data"]["nodes"].append(
            {
                "id": "orphan",
                "text": "孤立node",
                "node_type": "process",
                "bbox": {"x0": 0.1, "y0": 0.1, "x1": 0.2, "y1": 0.2},
            }
        )

        with self.assertRaisesRegex(ValueError, "到達できないnode"):
            validate_gold(gold, SCHEMA)

    def test_empty_decision_condition_is_rejected(self):
        gold = deepcopy(GOLD)
        decision_edge = next(
            edge for edge in gold["data"]["edges"] if edge["from"] == "decision"
        )
        decision_edge["condition"] = None

        with self.assertRaisesRegex(ValueError, "分岐条件は空"):
            validate_gold(gold, SCHEMA)

    def test_end_node_with_outgoing_edge_is_rejected(self):
        gold = deepcopy(GOLD)
        gold["data"]["edges"].append(
            {
                "from": "end",
                "to": "check",
                "condition": None,
                "bbox": {"x0": 0.1, "y0": 0.1, "x1": 0.2, "y1": 0.2},
            }
        )

        with self.assertRaisesRegex(ValueError, "end nodeにはoutgoing edge"):
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
