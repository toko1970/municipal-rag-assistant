from types import SimpleNamespace
import unittest

from src.llm_provider import GeminiProvider, MistralProvider, OpenAIProvider


class LLMProviderTest(unittest.TestCase):
    def test_normalizes_gemini_response(self):
        client = SimpleNamespace(
            invoke=lambda _prompt: SimpleNamespace(
                content="回答",
                usage_metadata={
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "total_tokens": 14,
                },
                response_metadata={"model_name": "gemini-test", "response_id": "g-1"},
            )
        )

        result = GeminiProvider("gemini-test", client=client).generate("質問")

        self.assertEqual(result.text, "回答")
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 4)
        self.assertEqual(result.request_id, "g-1")

    def test_normalizes_openai_responses_api(self):
        def request(url, api_key, payload):
            self.assertEqual(url, "https://api.openai.com/v1/responses")
            self.assertEqual(api_key, "test-key")
            self.assertFalse(payload["store"])
            return {
                "id": "o-1",
                "model": "gpt-5-mini-2026-01-01",
                "output": [
                    {"content": [{"type": "output_text", "text": "回答"}]}
                ],
                "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
            }

        result = OpenAIProvider(
            "gpt-5-mini", api_key="test-key", request_fn=request
        ).generate("質問")

        self.assertEqual(result.text, "回答")
        self.assertEqual(result.model, "gpt-5-mini-2026-01-01")
        self.assertEqual(result.total_tokens, 17)

    def test_normalizes_mistral_chat_completion(self):
        def request(_url, _api_key, payload):
            self.assertEqual(payload["temperature"], 0)
            return {
                "id": "m-1",
                "model": "mistral-small-latest",
                "choices": [{"message": {"content": "回答"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3},
            }

        result = MistralProvider(
            "mistral-small-latest", api_key="test-key", request_fn=request
        ).generate("質問")

        self.assertEqual(result.text, "回答")
        self.assertEqual(result.total_tokens, 11)
        self.assertEqual(result.request_id, "m-1")


if __name__ == "__main__":
    unittest.main()
