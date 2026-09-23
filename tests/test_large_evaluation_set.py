from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest

from eval.create_scenario_review_sheet import create_review_rows
from eval.freeze_large_evaluation_set import freeze_evaluation_set
from eval.generate_large_evaluation_set import generate_records
from eval.validate_large_evaluation_set import validate_rows


class LargeEvaluationSetTest(unittest.TestCase):
    def test_generated_set_has_500_unique_questions_and_100_scenarios(self):
        records = generate_records()

        summary = validate_rows(records)

        self.assertEqual(summary["questions"], 500)
        self.assertEqual(summary["scenarios"], 100)
        self.assertEqual(len({row["question"] for row in records}), 500)
        self.assertEqual(
            [row["question_id"] for row in records],
            [f"Q{number:03d}" for number in range(1, 501)],
        )
        self.assertEqual(
            {row["scenario_id"] for row in records},
            {f"S{number:03d}" for number in range(1, 101)},
        )
        self.assertEqual({row["review_status"] for row in records}, {"assistant_reviewed"})
        self.assertTrue(all(row["expected_answer_key"] for row in records))

    def test_unanswerable_questions_have_no_gold_document(self):
        records = generate_records()

        unanswerable = [
            row for row in records if row["expected_answer_type"] == "文書不足"
        ]

        self.assertEqual(len(unanswerable), 60)
        self.assertTrue(all(not row["expected_document_ids"] for row in unanswerable))
        self.assertTrue(all(not row["expected_evidence"] for row in unanswerable))

    def test_review_sheet_has_one_row_per_scenario(self):
        rows = create_review_rows()

        self.assertEqual(len(rows), 100)
        self.assertEqual(len({row["scenario_id"] for row in rows}), 100)
        self.assertEqual(
            sum(row["review_priority"] == "重点確認" for row in rows), 9
        )

    def test_freezes_only_fully_approved_review_set(self):
        rows = create_review_rows()
        for row in rows:
            row["user_decision"] = "承認"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = root / "review.csv"
            output_path = root / "questions.csv"
            manifest_path = root / "manifest.json"
            with review_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            manifest = freeze_evaluation_set(
                review_path=review_path,
                output_path=output_path,
                manifest_path=manifest_path,
            )

            with output_path.open(encoding="utf-8-sig", newline="") as file:
                frozen = list(csv.DictReader(file))
            self.assertEqual(
                {row["review_status"] for row in frozen}, {"user_approved"}
            )
            self.assertEqual(manifest["approved_scenarios"], 100)
            self.assertTrue(manifest_path.exists())


if __name__ == "__main__":
    unittest.main()
