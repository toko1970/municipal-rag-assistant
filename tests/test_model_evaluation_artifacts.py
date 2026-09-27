from collections import Counter
from pathlib import Path
import csv
import json
import unittest


RESULT_FILE = Path("eval/results/model_gemini_gemini-3.1-flash-lite_formal.csv")
FAILURE_FILE = Path("eval/results/model_gemini_3_1_failure_analysis.csv")
CACHE_FILE = Path("eval/results/model_evaluation_retrieval.jsonl")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class ModelEvaluationArtifactsTest(unittest.TestCase):
    def test_flash_lite_formal_result_matches_reported_metrics(self):
        rows = read_csv(RESULT_FILE)

        self.assertEqual(len(rows), 100)
        self.assertEqual(sum(int(row["classification_ok"]) for row in rows), 84)
        self.assertTrue(all(not row["generation_error"] for row in rows))

    def test_failure_analysis_covers_every_classification_mismatch(self):
        results = read_csv(RESULT_FILE)
        failures = read_csv(FAILURE_FILE)
        mismatch_ids = {
            row["question_id"] for row in results if row["classification_ok"] == "0"
        }

        self.assertEqual({row["question_id"] for row in failures}, mismatch_ids)
        self.assertEqual(
            Counter(row["primary_cause"] for row in failures),
            {
                "retrieval_failure": 7,
                "classification_only": 5,
                "generation_revision_interpretation": 2,
                "generation_date_interpretation": 1,
                "generation_conflict_resolution": 1,
            },
        )
        self.assertEqual(sum(int(row["content_ok"]) for row in failures), 5)

    def test_retrieval_cache_has_all_formal_questions_without_errors(self):
        with CACHE_FILE.open(encoding="utf-8") as file:
            rows = [json.loads(line) for line in file if line.strip()]

        self.assertEqual(len(rows), 100)
        self.assertEqual(len({row["question_id"] for row in rows}), 100)
        self.assertTrue(all(not row["retrieval_error"] for row in rows))


if __name__ == "__main__":
    unittest.main()
