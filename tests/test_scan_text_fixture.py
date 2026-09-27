from copy import deepcopy
from pathlib import Path
import unittest

from eval.validate_scan_text_fixture import (
    validate_gold,
    validate_manifest,
    validate_ocr_candidate,
)
from eval.validate_visual_fixture import load_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPOSITORY_ROOT / "design/schemas/scan-text-extraction-v1.schema.json"
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "eval/text_pdf_fixtures/manifests/scan_development_manifest.json"
)
GOLD_PATH = REPOSITORY_ROOT / "eval/text_pdf_fixtures/gold/scan_text_dev_001.json"


class ScanTextFixtureTest(unittest.TestCase):
    def test_committed_fixture_is_valid(self):
        manifest = validate_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(manifest["split"], "development")
        self.assertEqual(len(manifest["fixtures"]), 1)

    def test_expected_text_is_an_acceptable_ocr_candidate(self):
        gold = load_json(GOLD_PATH)

        validate_ocr_candidate(gold["expected_full_text"], gold)

    def test_altered_critical_value_is_rejected(self):
        gold = load_json(GOLD_PATH)
        candidate = gold["expected_full_text"].replace("30,000円以上", "30,000円未満")

        with self.assertRaisesRegex(ValueError, "OCR候補にcritical valueがありません"):
            validate_ocr_candidate(candidate, gold)

    def test_other_text_difference_is_rejected(self):
        gold = load_json(GOLD_PATH)
        candidate = gold["expected_full_text"].replace("確認書類", "必要書類")

        with self.assertRaisesRegex(ValueError, "OCR候補全文がgoldと一致しません"):
            validate_ocr_candidate(candidate, gold)

    def test_reversed_bbox_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        region = gold["pages"][0]["regions"][0]
        region["bbox"]["x1"] = region["bbox"]["x0"]

        with self.assertRaisesRegex(ValueError, "bboxはx0 < x1"):
            validate_gold(gold, load_json(SCHEMA_PATH))

    def test_scan_cannot_be_marked_as_automatically_approved(self):
        gold = deepcopy(load_json(GOLD_PATH))
        gold["confidence"]["review_required"] = False

        with self.assertRaisesRegex(ValueError, "Schema validationに失敗しました"):
            validate_gold(gold, load_json(SCHEMA_PATH))


if __name__ == "__main__":
    unittest.main()
