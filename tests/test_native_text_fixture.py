from copy import deepcopy
from pathlib import Path
import unittest

from eval.validate_native_text_fixture import (
    validate_document_content,
    validate_gold,
    validate_manifest,
)
from eval.validate_visual_fixture import load_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPOSITORY_ROOT / "design/schemas/native-text-extraction-v1.schema.json"
MANIFEST_PATH = REPOSITORY_ROOT / "eval/text_pdf_fixtures/manifests/development_manifest.json"
PDF_PATH = REPOSITORY_ROOT / "eval/text_pdf_fixtures/documents/native_text_dev_001.pdf"
GOLD_PATH = REPOSITORY_ROOT / "eval/text_pdf_fixtures/gold/native_text_dev_001.json"


class NativeTextFixtureTest(unittest.TestCase):
    def test_committed_fixture_is_valid(self):
        manifest = validate_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(manifest["split"], "development")
        self.assertEqual(len(manifest["fixtures"]), 1)

    def test_native_text_matches_gold_and_preserves_critical_values(self):
        gold = load_json(GOLD_PATH)

        validate_document_content(PDF_PATH, gold)
        self.assertEqual(
            gold["critical_values"],
            ["2026年4月1日", "翌月5日", "3営業日以内"],
        )

    def test_wrong_expected_text_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        gold["pages"][0]["expected_text"] += "改変"

        with self.assertRaisesRegex(ValueError, "抽出全文がgoldと一致しません"):
            validate_document_content(PDF_PATH, gold)

    def test_reversed_bbox_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        block = gold["pages"][0]["blocks"][0]
        block["bbox"]["x1"] = block["bbox"]["x0"]

        with self.assertRaisesRegex(ValueError, "bboxはx0 < x1"):
            validate_gold(gold, load_json(SCHEMA_PATH))

    def test_missing_critical_value_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        gold["critical_values"].append("存在しない金額")

        with self.assertRaisesRegex(ValueError, "critical valueが期待全文にありません"):
            validate_gold(gold, load_json(SCHEMA_PATH))


if __name__ == "__main__":
    unittest.main()
