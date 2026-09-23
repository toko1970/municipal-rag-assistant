import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eval.evaluate_answer_quality import (
    evaluate_answer_quality,
    extract_answer_type,
    save_results,
)


class AnswerQualityEvaluationTest(unittest.TestCase):
    def test_records_automatic_classification_and_pending_manual_review(self):
        questions = [
            {
                "question_id": "H01",
                "question": "支給日は？",
                "expected_answer_type": "根拠十分",
                "difficulty": "paraphrase",
            }
        ]

        def generate(_question):
            return {
                "answer": "回答分類: 根拠十分\n\n回答:\n21日です。",
                "references": [
                    {"document_id": "DOC-001", "heading": "給与支給日"}
                ],
            }

        records = evaluate_answer_quality(questions, generate_fn=generate)

        self.assertEqual(records[0]["predicted_answer_type"], "根拠十分")
        self.assertEqual(records[0]["classification_ok"], 1)
        self.assertEqual(records[0]["content_ok"], "")
        self.assertEqual(records[0]["no_hallucination"], "")
        self.assertEqual(records[0]["review_status"], "pending")
        self.assertEqual(records[0]["retrieved_document_ids"], "DOC-001")

        with TemporaryDirectory() as directory:
            output = Path(directory) / "answers.csv"
            save_results(records, output)
            with output.open(encoding="utf-8-sig", newline="") as file:
                saved = list(csv.DictReader(file))
        self.assertEqual(saved[0]["classification_ok"], "1")
        self.assertIn("21日", saved[0]["answer"])

    def test_records_generation_error_without_stopping_remaining_questions(self):
        questions = [
            {
                "question_id": "H01",
                "question": "質問",
                "expected_answer_type": "文書不足",
            }
        ]

        def fail(_question):
            raise RuntimeError("API error")

        record = evaluate_answer_quality(questions, generate_fn=fail)[0]

        self.assertEqual(record["predicted_answer_type"], "生成失敗")
        self.assertEqual(record["classification_ok"], 0)
        self.assertEqual(record["generation_error"], "RuntimeError: API error")

    def test_extracts_only_supported_answer_types(self):
        self.assertEqual(extract_answer_type("回答分類： 判断要"), "判断要")
        self.assertEqual(extract_answer_type("分類なし"), "抽出失敗")

    def test_assigns_compatible_id_to_legacy_question_set(self):
        record = evaluate_answer_quality(
            [{"question": "質問", "expected_answer_type": "根拠十分"}],
            generate_fn=lambda _question: {
                "answer": "回答分類: 根拠十分",
                "references": [],
            },
        )[0]

        self.assertEqual(record["question_id"], "row-001")


if __name__ == "__main__":
    unittest.main()
