from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eval.evaluate_models import (
    evaluate_questions,
    estimate_cost,
    is_rate_limit_error,
    load_results,
    prepare_retrieval_cases,
)
from src.llm_provider import LLMResult


class FakeProvider:
    provider_name = "openai"
    model = "gpt-5-mini"

    def __init__(self):
        self.calls = 0

    def generate(self, _prompt):
        self.calls += 1
        return LLMResult(
            provider=self.provider_name,
            model=self.model,
            text="回答分類: 根拠十分\n\n回答:\n21日です。",
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            request_id="request-1",
        )


class ModelEvaluationTest(unittest.TestCase):
    def test_detects_rate_limit_errors(self):
        self.assertTrue(is_rate_limit_error("429 RESOURCE_EXHAUSTED"))
        self.assertTrue(is_rate_limit_error("Too Many Requests"))
        self.assertFalse(is_rate_limit_error("500 Internal Server Error"))

    def test_estimates_model_cost_from_recorded_tokens(self):
        self.assertEqual(estimate_cost("openai", "gpt-5-mini", 100, 20), "0.00006500")
        self.assertEqual(estimate_cost("unknown", "model", 100, 20), "")

    def test_saves_checkpoint_and_resumes_completed_question(self):
        questions = [
            {
                "question_id": "Q001",
                "scenario_id": "S001",
                "question": "支給日は？",
                "topic": "給与支給日",
                "difficulty": "direct",
                "variant_type": "formal",
                "expected_answer_type": "根拠十分",
                "expected_answer_key": "毎月21日。",
            }
        ]
        cache = {
            "Q001": {
                "question_id": "Q001",
                "question": "支給日は？",
                "context": "給与は21日に支給する。",
                "references": [
                    {"document_id": "DOC-001", "heading": "給与支給日"}
                ],
                "retrieval_error": "",
            }
        }
        provider = FakeProvider()

        with TemporaryDirectory() as directory:
            output = Path(directory) / "result.csv"
            first = evaluate_questions(questions, cache, provider, output)
            second = evaluate_questions(questions, cache, provider, output)

            self.assertEqual(provider.calls, 1)
            self.assertEqual(first[0]["classification_ok"], 1)
            self.assertEqual(second[0]["request_id"], "request-1")
            self.assertEqual(len(load_results(output)), 1)

    def test_retries_failed_retrieval_cache_entry(self):
        questions = [{"question_id": "Q001", "question": "支給日は？"}]
        calls = []

        def retrieve(question):
            calls.append(question)
            return []

        with TemporaryDirectory() as directory:
            cache_path = Path(directory) / "cache.jsonl"
            cache_path.write_text(
                '{"question_id":"Q001","question":"支給日は？",'
                '"context":"","references":[],"retrieval_error":"network"}\n',
                encoding="utf-8",
            )

            cache = prepare_retrieval_cases(questions, cache_path, retrieve_fn=retrieve)

            self.assertEqual(calls, ["支給日は？"])
            self.assertEqual(cache["Q001"]["retrieval_error"], "")

    def test_stops_after_rate_limit_and_keeps_checkpoint(self):
        class LimitedProvider(FakeProvider):
            def generate(self, _prompt):
                self.calls += 1
                raise RuntimeError("429 RESOURCE_EXHAUSTED")

        questions = [
            {
                "question_id": question_id,
                "scenario_id": scenario_id,
                "question": "質問",
                "expected_answer_type": "根拠十分",
            }
            for question_id, scenario_id in (("Q001", "S001"), ("Q006", "S002"))
        ]
        cache = {
            row["question_id"]: {
                "context": "文書",
                "references": [],
                "retrieval_error": "",
            }
            for row in questions
        }
        provider = LimitedProvider()

        with TemporaryDirectory() as directory:
            output = Path(directory) / "result.csv"
            records = evaluate_questions(questions, cache, provider, output)

        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(records), 1)
        self.assertIn("429", records[0]["generation_error"])


if __name__ == "__main__":
    unittest.main()
