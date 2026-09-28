from types import SimpleNamespace
import unittest

from langchain_core.messages import HumanMessage

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

    def test_uses_gemini_native_json_schema(self):
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        }
        raw = SimpleNamespace(
            usage_metadata={"input_tokens": 7, "output_tokens": 2},
            response_metadata={"model_name": "gemini-structured", "response_id": "g-2"},
        )

        class Runnable:
            def invoke(self, prompt):
                self.prompt = prompt
                return {
                    "raw": raw,
                    "parsed": {"answer": "21日"},
                    "parsing_error": None,
                }

        class Client:
            def __init__(self):
                self.runnable = Runnable()

            def with_structured_output(self, actual_schema, **kwargs):
                self.schema = actual_schema
                self.kwargs = kwargs
                return self.runnable

        client = Client()
        result = GeminiProvider("gemini-test", client=client).generate_structured(
            "質問", schema
        )

        self.assertEqual(client.schema, schema)
        self.assertEqual(client.kwargs["method"], "json_schema")
        self.assertTrue(client.kwargs["include_raw"])
        self.assertEqual(result.data, {"answer": "21日"})
        self.assertEqual(result.total_tokens, 9)
        self.assertEqual(result.request_id, "g-2")

    def test_translates_json_schema_const_for_gemini(self):
        schema = {
            "type": "object",
            "properties": {"schema_version": {"const": "1.0"}},
        }

        class Runnable:
            def invoke(self, _prompt):
                return {
                    "raw": SimpleNamespace(
                        usage_metadata={}, response_metadata={}
                    ),
                    "parsed": {"schema_version": "1.0"},
                    "parsing_error": None,
                }

        class Client:
            def with_structured_output(self, actual_schema, **_kwargs):
                self.schema = actual_schema
                return Runnable()

        client = Client()
        GeminiProvider("gemini-test", client=client).generate_structured(
            "質問", schema
        )

        assert client.schema["properties"]["schema_version"] == {
            "enum": ["1.0"],
            "type": "string",
        }
        assert schema["properties"]["schema_version"] == {"const": "1.0"}

    def test_sends_inline_image_for_structured_gemini_output(self):
        class Runnable:
            def invoke(self, content):
                self.content = content
                return {
                    "raw": SimpleNamespace(
                        usage_metadata={}, response_metadata={}
                    ),
                    "parsed": {"answer": "図表"},
                    "parsing_error": None,
                }

        class Client:
            def __init__(self):
                self.runnable = Runnable()

            def with_structured_output(self, _schema, **_kwargs):
                return self.runnable

        client = Client()
        result = GeminiProvider(
            "gemini-test", client=client
        ).generate_structured_multimodal(
            "画像を確認してください",
            {"type": "object"},
            image=b"png-bytes",
            mime_type="image/png",
        )

        assert result.data == {"answer": "図表"}
        messages = client.runnable.content
        assert len(messages) == 1
        message = messages[0]
        assert isinstance(message, HumanMessage)
        assert message.content[0] == {
            "type": "text",
            "text": "画像を確認してください",
        }
        assert message.content[1]["type"] == "media"
        assert message.content[1]["mime_type"] == "image/png"
        assert message.content[1]["data"] == "cG5nLWJ5dGVz"

    def test_sends_multiple_images_for_structured_gemini_output(self):
        class Runnable:
            def invoke(self, content):
                self.content = content
                return {
                    "raw": SimpleNamespace(usage_metadata={}, response_metadata={}),
                    "parsed": {"answer": "複数図表"},
                    "parsing_error": None,
                }

        class Client:
            def __init__(self):
                self.runnable = Runnable()

            def with_structured_output(self, _schema, **_kwargs):
                return self.runnable

        client = Client()
        GeminiProvider("gemini-test", client=client).generate_structured_with_media(
            "2枚を確認してください",
            {"type": "object"},
            media=[(b"one", "image/png"), (b"two", "image/jpeg")],
        )

        content = client.runnable.content[0].content
        assert [item["type"] for item in content] == ["text", "media", "media"]
        assert content[1]["data"] == "b25l"
        assert content[2]["mime_type"] == "image/jpeg"

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
