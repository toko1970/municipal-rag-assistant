import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from eval.evaluate_retrieval import evaluate_retrieval, save_results


class RetrievalEvaluationTest(unittest.TestCase):
    def test_saves_each_question_and_its_ranked_search_outcome(self):
        questions = [
            {"question": "質問A", "expected_document_id": "DOC-001", "difficulty": "paraphrase"},
            {"question": "質問B", "expected_document_id": "DOC-003", "difficulty": "practical"},
        ]
        search_results = [
            [
                (SimpleNamespace(metadata={"document_id": "DOC-002"}), 0.1),
                (SimpleNamespace(metadata={"document_id": "DOC-001"}), 0.2),
            ],
            [(SimpleNamespace(metadata={"document_id": "DOC-004"}), 0.1)],
        ]

        with patch("eval.evaluate_retrieval.retrieve_documents_with_score", side_effect=search_results):
            records = evaluate_retrieval(questions)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "results" / "retrieval.csv"
            save_results(records, output)
            with output.open(encoding="utf-8-sig", newline="") as f:
                saved = list(csv.DictReader(f))

        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]["retrieved_document_ids"], "DOC-002|DOC-001")
        self.assertEqual(saved[0]["top_k"], "5")
        self.assertEqual([saved[0][f"hit_at_{k}"] for k in (1, 3, 5)], ["0", "1", "1"])
        self.assertEqual([saved[1][f"hit_at_{k}"] for k in (1, 3, 5)], ["0", "0", "0"])
        self.assertEqual(saved[0]["difficulty"], "paraphrase")

    def test_rejects_empty_question_set(self):
        with self.assertRaisesRegex(ValueError, "評価質問がありません"):
            evaluate_retrieval([])


if __name__ == "__main__":
    unittest.main()
