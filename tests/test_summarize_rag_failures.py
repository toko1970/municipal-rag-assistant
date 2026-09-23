import unittest

from eval.summarize_rag_failures import classify_failure, summarize_failures


def answer_record(**overrides):
    record = {
        "question_id": "H01",
        "question": "質問",
        "expected_answer_type": "根拠十分",
        "classification_ok": "1",
        "content_ok": "1",
        "no_hallucination": "1",
        "generation_error": "",
    }
    record.update(overrides)
    return record


class RagFailureSummaryTest(unittest.TestCase):
    def test_classifies_answerable_failures_in_pipeline_order(self):
        retrieval_miss = {"evidence_hit_at_5": "0"}
        retrieval_hit = {"evidence_hit_at_5": "1"}

        self.assertEqual(
            classify_failure(answer_record(), retrieval_miss), "retrieval_failure"
        )
        self.assertEqual(
            classify_failure(answer_record(content_ok="0"), retrieval_hit),
            "answer_generation_failure",
        )
        self.assertEqual(
            classify_failure(answer_record(classification_ok="0"), retrieval_hit),
            "classification_failure",
        )
        self.assertEqual(classify_failure(answer_record(), retrieval_hit), "success")

    def test_separates_handled_and_failed_unanswerable_questions(self):
        retrieval = {"evidence_hit_at_5": ""}
        handled = answer_record(expected_answer_type="文書不足")
        failed = answer_record(
            expected_answer_type="文書不足",
            classification_ok="0",
            no_hallucination="0",
        )

        self.assertEqual(
            classify_failure(handled, retrieval), "unanswerable_handled"
        )
        self.assertEqual(classify_failure(failed, retrieval), "unanswerable_failed")

    def test_requires_completed_manual_review(self):
        with self.assertRaisesRegex(ValueError, "content_ok が未判定"):
            classify_failure(answer_record(content_ok=""), {"evidence_hit_at_5": "1"})

    def test_generation_error_does_not_require_manual_review(self):
        answer = answer_record(
            generation_error="RuntimeError: API error",
            content_ok="",
            no_hallucination="",
        )

        self.assertEqual(
            classify_failure(answer, {"evidence_hit_at_5": ""}),
            "generation_error",
        )

    def test_requires_identical_question_sets(self):
        with self.assertRaisesRegex(ValueError, "質問IDが一致しません"):
            summarize_failures(
                {"H01": answer_record()},
                {
                    "H02": {
                        "question_id": "H02",
                        "question": "別の質問",
                        "evidence_hit_at_5": "1",
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()
