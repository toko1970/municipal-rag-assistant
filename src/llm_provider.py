"""回答生成モデルを共通形式で呼び出すためのプロバイダー。"""

from dataclasses import asdict, dataclass
from typing import Callable, Protocol
from urllib.request import Request, urlopen
import json

from langchain_google_genai import ChatGoogleGenerativeAI

from config import GOOGLE_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY


@dataclass(frozen=True)
class LLMResult:
    provider: str
    model: str
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    request_id: str = ""

    def metadata(self) -> dict:
        data = asdict(self)
        data.pop("text")
        return data


class LLMProvider(Protocol):
    provider_name: str
    model: str

    def generate(self, prompt: str) -> LLMResult: ...


def _int_value(mapping: dict, *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return int(value)
    return 0


def _text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


class GeminiProvider:
    provider_name = "gemini"

    def __init__(self, model: str, api_key=None, client=None, temperature: float = 0):
        self.model = model
        self.client = client or ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key or GOOGLE_API_KEY,
            temperature=temperature,
        )

    def generate(self, prompt: str) -> LLMResult:
        response = self.client.invoke(prompt)
        usage = dict(getattr(response, "usage_metadata", None) or {})
        metadata = dict(getattr(response, "response_metadata", None) or {})
        if not usage:
            usage = dict(metadata.get("usage_metadata") or {})
        input_tokens = _int_value(usage, "input_tokens", "prompt_token_count")
        output_tokens = _int_value(usage, "output_tokens", "candidates_token_count")
        total_tokens = _int_value(usage, "total_tokens", "total_token_count")
        return LLMResult(
            provider=self.provider_name,
            model=str(metadata.get("model_name") or self.model),
            text=_text_content(response.content),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens or input_tokens + output_tokens,
            request_id=str(metadata.get("response_id") or ""),
        )


def post_json(url: str, api_key: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


class OpenAIProvider:
    provider_name = "openai"
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        request_fn: Callable[[str, str, dict], dict] = post_json,
    ):
        self.model = model
        self.api_key = api_key or OPENAI_API_KEY
        self.request_fn = request_fn
        if not self.api_key:
            raise ValueError("OPENAI_API_KEYが設定されていません")

    def generate(self, prompt: str) -> LLMResult:
        data = self.request_fn(
            self.endpoint,
            self.api_key,
            {"model": self.model, "input": prompt, "store": False},
        )
        text_parts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text_parts.append(str(content.get("text", "")))
        usage = data.get("usage") or {}
        input_tokens = _int_value(usage, "input_tokens")
        output_tokens = _int_value(usage, "output_tokens")
        return LLMResult(
            provider=self.provider_name,
            model=str(data.get("model") or self.model),
            text="".join(text_parts),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=_int_value(usage, "total_tokens")
            or input_tokens + output_tokens,
            request_id=str(data.get("id") or ""),
        )


class MistralProvider:
    provider_name = "mistral"
    endpoint = "https://api.mistral.ai/v1/chat/completions"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        request_fn: Callable[[str, str, dict], dict] = post_json,
        temperature: float = 0,
    ):
        self.model = model
        self.api_key = api_key or MISTRAL_API_KEY
        self.request_fn = request_fn
        self.temperature = temperature
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEYが設定されていません")

    def generate(self, prompt: str) -> LLMResult:
        data = self.request_fn(
            self.endpoint,
            self.api_key,
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
            },
        )
        message = data.get("choices", [{}])[0].get("message", {})
        usage = data.get("usage") or {}
        input_tokens = _int_value(usage, "prompt_tokens", "input_tokens")
        output_tokens = _int_value(usage, "completion_tokens", "output_tokens")
        return LLMResult(
            provider=self.provider_name,
            model=str(data.get("model") or self.model),
            text=_text_content(message.get("content", "")),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=_int_value(usage, "total_tokens")
            or input_tokens + output_tokens,
            request_id=str(data.get("id") or ""),
        )


def create_provider(provider: str, model: str) -> LLMProvider:
    if provider == "gemini":
        return GeminiProvider(model)
    if provider == "openai":
        return OpenAIProvider(model)
    if provider == "mistral":
        return MistralProvider(model)
    raise ValueError(f"未対応のプロバイダーです: {provider}")
