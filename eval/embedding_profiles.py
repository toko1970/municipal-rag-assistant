"""Embedding profiles and adapters used by isolated retrieval experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingProfile:
    key: str
    provider: str
    model: str
    dimensions: int
    collection_name: str
    query_prefix: str
    document_prefix: str
    remote: bool

    def manifest(self) -> dict[str, object]:
        return asdict(self)


PROFILES = {
    "gemini-embedding-001": EmbeddingProfile(
        key="gemini-embedding-001",
        provider="google",
        model="gemini-embedding-001",
        dimensions=3072,
        collection_name="municipal_docs_eval_gemini_embedding_001_v1",
        query_prefix="",
        document_prefix="",
        remote=True,
    ),
    "gemini-embedding-2-768": EmbeddingProfile(
        key="gemini-embedding-2-768",
        provider="google",
        model="gemini-embedding-2",
        dimensions=768,
        collection_name="municipal_docs_eval_gemini_embedding_2_768_v1",
        query_prefix="task: question answering | query: ",
        document_prefix="title: none | text: ",
        remote=True,
    ),
    "ruri-v3-310m": EmbeddingProfile(
        key="ruri-v3-310m",
        provider="huggingface-local",
        model="cl-nagoya/ruri-v3-310m",
        dimensions=768,
        collection_name="municipal_docs_eval_ruri_v3_310m_v1",
        query_prefix="検索クエリ: ",
        document_prefix="検索文書: ",
        remote=False,
    ),
}


class ExperimentEmbedder(Protocol):
    request_count: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class GeminiOneEmbedder:
    def __init__(self, profile: EmbeddingProfile, api_key: str) -> None:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        self.profile = profile
        self.client = GoogleGenerativeAIEmbeddings(
            model=profile.model,
            google_api_key=api_key,
        )
        self.request_count = 0
        self.runtime_device = "remote"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.request_count += 1
        return self.client.embed_documents(
            texts,
            batch_size=100,
            task_type="RETRIEVAL_DOCUMENT",
        )

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        self.request_count += 1
        return self.client.embed_documents(
            texts,
            batch_size=100,
            task_type="RETRIEVAL_QUERY",
        )


class GeminiTwoEmbedder:
    def __init__(
        self, profile: EmbeddingProfile, api_key: str, client=None
    ) -> None:
        self.profile = profile
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self.client = client
        self.request_count = 0
        self.runtime_device = "remote"

    def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        from google.genai import types

        vectors: list[list[float]] = []
        for offset in range(0, len(texts), 100):
            batch = texts[offset : offset + 100]
            contents = [
                types.Content(parts=[types.Part(text=f"{prefix}{text}")])
                for text in batch
            ]
            response = self.client.models.embed_content(
                model=self.profile.model,
                contents=contents,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.profile.dimensions
                ),
            )
            self.request_count += 1
            vectors.extend([list(item.values or []) for item in response.embeddings])
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, self.profile.document_prefix)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, self.profile.query_prefix)


class RuriEmbedder:
    def __init__(self, profile: EmbeddingProfile, device: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "Ruriの実行にはrequirements-ruri.txtの追加依存が必要です"
            ) from error

        self.profile = profile
        self.model = SentenceTransformer(profile.model, device=device)
        self.request_count = 0
        self.runtime_device = str(self.model.device)

    def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        self.request_count += 1
        result = self.model.encode(
            [f"{prefix}{text}" for text in texts],
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        return result.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, self.profile.document_prefix)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, self.profile.query_prefix)


def create_embedder(
    profile: EmbeddingProfile,
    *,
    api_key: str | None = None,
    device: str | None = None,
) -> ExperimentEmbedder:
    if profile.key == "gemini-embedding-001":
        if not api_key:
            raise ValueError("Gemini profileにはGOOGLE_API_KEYが必要です")
        return GeminiOneEmbedder(profile, api_key)
    if profile.key == "gemini-embedding-2-768":
        if not api_key:
            raise ValueError("Gemini profileにはGOOGLE_API_KEYが必要です")
        return GeminiTwoEmbedder(profile, api_key)
    if profile.key == "ruri-v3-310m":
        return RuriEmbedder(profile, device=device)
    raise ValueError(f"未対応のEmbedding profileです: {profile.key}")
