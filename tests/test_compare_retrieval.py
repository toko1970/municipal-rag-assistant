import unittest
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from eval.compare_retrieval import compare_results, load_results


class ComparisonTest(unittest.TestCase):
    def test_counts_improvements_and_regressions_on_identical_questions(self):
        common = {
            "question": "質問",
            "expected_document_ids": "DOC-001",
            "expected_evidence": "DOC-001::見出し",
            "retrieval_applicable": "1",
            "difficulty": "near_miss",
            "hit_at_3": "1",
            "hit_at_5": "1",
        }
        before = {"H01": {**common, "evidence_hit_at_3": "0", "evidence_hit_at_5": "1"}}
        after = {"H01": {**common, "evidence_hit_at_3": "1", "evidence_hit_at_5": "1"}}

        summary, changes = compare_results(before, after)

        self.assertIn(
            {"metric": "evidence_hit_at_3", "before": 0, "after": 1, "total": 1},
            summary,
        )
        self.assertEqual(changes[0]["question_id"], "H01")

    def test_rejects_changed_answer_key(self):
        before = {"H01": {"question": "質問", "expected_document_ids": "DOC-001"}}
        after = {"H01": {"question": "質問", "expected_document_ids": "DOC-002"}}

        with self.assertRaisesRegex(ValueError, "評価条件が異なります"):
            compare_results(before, after)

    def test_legacy_results_can_use_unique_question_text_as_key(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.csv"
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["question_id", "question"])
                writer.writeheader()
                writer.writerow({"question_id": "", "question": "元の実務質問"})

            records = load_results(path)

        self.assertEqual(list(records), ["元の実務質問"])

    def test_rejects_different_metric_denominators(self):
        common = {"question": "質問", "expected_document_ids": "DOC-001"}
        before = {"H01": {**common, "hit_at_3": "1"}}
        after = {"H01": {**common, "hit_at_3": ""}}

        with self.assertRaisesRegex(ValueError, "評価対象が異なります"):
            compare_results(before, after)


if __name__ == "__main__":
    unittest.main()
