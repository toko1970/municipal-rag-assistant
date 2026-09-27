from copy import deepcopy
from pathlib import Path
import unittest

from PIL import Image

from eval.validate_low_quality_scan_fixture import (
    grayscale_dynamic_range,
    validate_gold,
    validate_image_quality,
    validate_manifest,
)
from eval.validate_visual_fixture import load_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPOSITORY_ROOT / "design/schemas/low-quality-scan-v1.schema.json"
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "eval/text_pdf_fixtures/manifests/low_quality_development_manifest.json"
)
GOLD_PATH = (
    REPOSITORY_ROOT / "eval/text_pdf_fixtures/gold/low_quality_scan_dev_001.json"
)


class LowQualityScanFixtureTest(unittest.TestCase):
    def test_committed_fixture_is_valid(self):
        manifest = validate_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(manifest["split"], "development")
        self.assertEqual(len(manifest["fixtures"]), 1)

    def test_low_quality_image_has_less_range_than_clean_reference(self):
        manifest = load_json(MANIFEST_PATH)
        fixture = manifest["fixtures"][0]
        low_path = REPOSITORY_ROOT / fixture["source_image"]["path"]
        clean_path = (
            REPOSITORY_ROOT
            / manifest["clean_reference"]["source_image"]["path"]
        )
        with Image.open(low_path) as low_image, Image.open(clean_path) as clean_image:
            self.assertLess(
                grayscale_dynamic_range(low_image),
                grayscale_dynamic_range(clean_image),
            )

    def test_ready_extraction_result_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        gold["expected_gate"]["extraction_result"] = "READY"

        with self.assertRaisesRegex(ValueError, "Schema validationに失敗しました"):
            validate_gold(gold, load_json(SCHEMA_PATH))

    def test_ready_document_status_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        gold["expected_gate"]["document_status"] = "READY"

        with self.assertRaisesRegex(ValueError, "Schema validationに失敗しました"):
            validate_gold(gold, load_json(SCHEMA_PATH))

    def test_missing_low_contrast_reason_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        gold["expected_gate"]["review_reasons"] = []

        with self.assertRaisesRegex(ValueError, "Schema validationに失敗しました"):
            validate_gold(gold, load_json(SCHEMA_PATH))

    def test_wrong_quality_measurement_is_rejected(self):
        manifest = load_json(MANIFEST_PATH)
        fixture = manifest["fixtures"][0]
        image_path = REPOSITORY_ROOT / fixture["source_image"]["path"]
        gold = deepcopy(load_json(GOLD_PATH))
        gold["quality_assessment"]["measurement"]["value"] += 1
        clean_range = manifest["clean_reference"]["source_image"][
            "grayscale_dynamic_range"
        ]

        with self.assertRaisesRegex(ValueError, "測定値がgoldと一致しません"):
            validate_image_quality(
                image_path,
                fixture["source_image"],
                gold,
                clean_range,
            )

    def test_reversed_bbox_is_rejected(self):
        gold = deepcopy(load_json(GOLD_PATH))
        region = gold["pages"][0]["regions"][0]
        region["bbox"]["x1"] = region["bbox"]["x0"]

        with self.assertRaisesRegex(ValueError, "bboxはx0 < x1"):
            validate_gold(gold, load_json(SCHEMA_PATH))


if __name__ == "__main__":
    unittest.main()
