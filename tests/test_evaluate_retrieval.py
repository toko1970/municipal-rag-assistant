import csv
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from eval.evaluate_retrieval import evaluate_retrieval, save_results


class RetrievalEvaluationTest(unittest.TestCase):
    def test_saves_each_question_and_its_ranked_search_outcome(self):
        questions = [
            {
                "question": "質問A",
                "expected_document_id": "DOC-001",
                "difficulty": "paraphrase",
            },
            {
                "question": "質問B",
                "expected_document_id": "DOC-003",
                "difficulty": "practical",
            },
        ]
        search_results = [
            [
                (SimpleNamespace(metadata={"document_id": "DOC-002"}), 0.1),
                (SimpleNamespace(metadata={"document_id": "DOC-001"}), 0.2),
            ],
            [(SimpleNamespace(metadata={"document_id": "DOC-004"}), 0.1)],
        ]

        with patch(
            "eval.evaluate_retrieval.retrieve_documents_with_score",
            side_effect=search_results,
        ):
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

    def test_requires_all_documents_and_excludes_unanswerable_questions_from_recall(
        self,
    ):
        questions = [
            {
                "question_id": "H01",
                "question": "二つの文書が必要な質問",
                "expected_document_ids": "DOC-002|DOC-005",
                "expected_evidence": "DOC-002::通勤手当|DOC-005::改正後",
                "expected_answer_type": "根拠十分",
            },
            {
                "question_id": "H02",
                "question": "文書に答えがない質問",
                "expected_document_ids": "",
                "expected_answer_type": "文書不足",
            },
        ]
        search_results = [
            [
                (
                    SimpleNamespace(
                        metadata={"document_id": "DOC-002", "見出し1": "通勤手当"}
                    ),
                    0.1,
                ),
                (SimpleNamespace(metadata={"document_id": "DOC-003"}), 0.2),
                (
                    SimpleNamespace(
                        metadata={"document_id": "DOC-005", "見出し2": "改正後"}
                    ),
                    0.3,
                ),
            ],
            [(SimpleNamespace(metadata={"document_id": "DOC-001"}), 0.1)],
        ]

        output = StringIO()
        with patch(
            "eval.evaluate_retrieval.retrieve_documents_with_score",
            side_effect=search_results,
        ):
            with redirect_stdout(output):
                records = evaluate_retrieval(questions)

        self.assertEqual(records[0]["document_recall_at_1"], 0.5)
        self.assertEqual(records[0]["hit_at_1"], 0)
        self.assertEqual(records[0]["hit_at_3"], 1)
        self.assertEqual(records[0]["evidence_recall_at_1"], 0.5)
        self.assertEqual(records[0]["evidence_hit_at_3"], 1)
        self.assertEqual(records[0]["retrieved_headings"], "通勤手当||改正後")
        self.assertEqual(records[1]["retrieval_applicable"], 0)
        self.assertEqual(records[1]["hit_at_3"], "")
        self.assertIn("検索評価対象: 1、文書不足: 1", output.getvalue())
        self.assertIn("全必要文書Hit@3: 1.00 (1/1)", output.getvalue())
        self.assertIn("全根拠見出しHit@3: 1.00 (1/1)", output.getvalue())

    def test_rejects_positive_question_without_required_document(self):
        with self.assertRaisesRegex(ValueError, "正解文書IDがありません"):
            evaluate_retrieval(
                [{"question": "質問", "expected_answer_type": "根拠十分"}]
            )

    def test_wrong_section_in_right_document_is_not_evidence_hit(self):
        question = {
            "question": "改正後の条件は？",
            "expected_document_ids": "DOC-005",
            "expected_evidence": "DOC-005::住居手当の改正 > 改正後",
            "expected_answer_type": "根拠十分",
        }
        results = [
            (
                SimpleNamespace(
                    metadata={"document_id": "DOC-005", "見出し2": "改正前"}
                ),
                0.1,
            )
        ]

        with patch(
            "eval.evaluate_retrieval.retrieve_documents_with_score",
            return_value=results,
        ):
            with redirect_stdout(StringIO()):
                record = evaluate_retrieval([question])[0]

        self.assertEqual(record["hit_at_1"], 1)
        self.assertEqual(record["evidence_hit_at_1"], 0)

    def test_rejects_empty_question_set(self):
        with self.assertRaisesRegex(ValueError, "評価質問がありません"):
            evaluate_retrieval([])


if __name__ == "__main__":
    unittest.main()
