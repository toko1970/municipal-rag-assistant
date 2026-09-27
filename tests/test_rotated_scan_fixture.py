from copy import deepcopy
from pathlib import Path
import unittest

from eval.validate_rotated_scan_fixture import (
    validate_document_content,
    validate_gold,
    validate_manifest,
)
from eval.validate_visual_fixture import load_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPOSITORY_ROOT / "design/schemas/rotated-scan-extraction-v1.schema.json"
)
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "eval/text_pdf_fixtures/manifests/rotation_development_manifest.json"
)
GOLD_90_PATH = (
    REPOSITORY_ROOT / "eval/text_pdf_fixtures/gold/rotated_scan_dev_090.json"
)
PDF_90_PATH = (
    REPOSITORY_ROOT / "eval/text_pdf_fixtures/documents/rotated_scan_dev_090.pdf"
)


class RotatedScanFixtureTest(unittest.TestCase):
    def test_committed_rotation_fixtures_are_valid(self):
        manifest = validate_manifest(MANIFEST_PATH, REPOSITORY_ROOT)

        self.assertEqual(
            [item["rotation_degrees"] for item in manifest["fixtures"]],
            [90, 180, 270],
        )

    def test_every_normalized_page_matches_the_upright_reference(self):
        manifest = load_json(MANIFEST_PATH)
        reference_hash = manifest["source_fixture"]["upright_reference_page"][
            "sha256"
        ]

        self.assertTrue(
            all(
                item["normalized_page"]["sha256"] == reference_hash
                for item in manifest["fixtures"]
            )
        )

    def test_wrong_rotation_is_rejected_against_the_pdf(self):
        gold = deepcopy(load_json(GOLD_90_PATH))
        gold["input_characteristics"]["rotation_degrees"] = 180
        manifest = load_json(MANIFEST_PATH)
        source_image = manifest["source_fixture"]["source_image"]

        with self.assertRaisesRegex(ValueError, "PDF rotationがgoldと一致しません"):
            validate_document_content(PDF_90_PATH, gold, source_image)

    def test_zero_degree_is_not_a_rotated_fixture(self):
        gold = deepcopy(load_json(GOLD_90_PATH))
        gold["input_characteristics"]["rotation_degrees"] = 0

        with self.assertRaisesRegex(ValueError, "Schema validationに失敗しました"):
            validate_gold(gold, load_json(SCHEMA_PATH))

    def test_reversed_upright_bbox_is_rejected(self):
        gold = deepcopy(load_json(GOLD_90_PATH))
        region = gold["pages"][0]["regions"][0]
        region["bbox"]["y1"] = region["bbox"]["y0"]

        with self.assertRaisesRegex(ValueError, "bboxはx0 < x1"):
            validate_gold(gold, load_json(SCHEMA_PATH))

    def test_rotated_scan_cannot_be_automatically_approved(self):
        gold = deepcopy(load_json(GOLD_90_PATH))
        gold["confidence"]["review_required"] = False

        with self.assertRaisesRegex(ValueError, "Schema validationに失敗しました"):
            validate_gold(gold, load_json(SCHEMA_PATH))


if __name__ == "__main__":
    unittest.main()
