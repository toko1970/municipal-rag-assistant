from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.compare_embedding_models import (
    load_or_create_vectors,
    percentile_95,
    retrieval_mrr,
)
from eval.embedding_profiles import PROFILES, GeminiTwoEmbedder


def test_embedding_profiles_keep_candidate_collections_separate() -> None:
    profiles = list(PROFILES.values())

    assert len({profile.collection_name for profile in profiles}) == len(profiles)
    assert PROFILES["gemini-embedding-2-768"].query_prefix.startswith(
        "task: question answering"
    )
    assert PROFILES["ruri-v3-310m"].document_prefix == "検索文書: "


def test_vector_cache_validates_profile_input_and_dimensions(tmp_path: Path) -> None:
    profile = PROFILES["ruri-v3-310m"]
    path = tmp_path / "vectors.json"
    calls = []

    def embed(texts):
        calls.append(texts)
        return [[0.0] * profile.dimensions for _ in texts]

    vectors, cache_hit, _elapsed = load_or_create_vectors(
        path,
        profile=profile,
        kind="query",
        ids=["Q1:hash"],
        texts=["質問"],
        embed=embed,
    )
    cached, cached_hit, cached_elapsed = load_or_create_vectors(
        path,
        profile=profile,
        kind="query",
        ids=["Q1:hash"],
        texts=["質問"],
        embed=embed,
    )

    assert len(vectors[0]) == 768
    assert cached == vectors
    assert not cache_hit
    assert cached_hit
    assert cached_elapsed is None
    assert calls == [["質問"]]

    with pytest.raises(ValueError, match="条件が一致しません"):
        load_or_create_vectors(
            path,
            profile=profile,
            kind="query",
            ids=["Q2:changed"],
            texts=["別の質問"],
            embed=embed,
        )


def test_retrieval_mrr_uses_first_expected_evidence_rank() -> None:
    records = [
        {
            "expected_evidence": "DOC-1::節A|DOC-1::節B",
            "retrieved_document_ids": "DOC-2|DOC-1|DOC-1",
            "retrieved_headings": "別節|節B|節A",
        },
        {
            "expected_evidence": "DOC-3::節C",
            "retrieved_document_ids": "DOC-1",
            "retrieved_headings": "節A",
        },
    ]

    assert retrieval_mrr(records) == 0.25
    assert percentile_95([0.1, 0.2, 0.3]) == 0.3


def test_gemini_two_uses_separate_contents_and_asymmetric_prefixes() -> None:
    calls = []

    def embed_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.0] * 768)]
        )

    client = SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))
    embedder = GeminiTwoEmbedder(
        PROFILES["gemini-embedding-2-768"], "unused", client=client
    )

    embedder.embed_queries(["期限は？"])
    embedder.embed_documents(["提出期限は14日以内。"])

    query_text = calls[0]["contents"][0].parts[0].text
    document_text = calls[1]["contents"][0].parts[0].text
    assert query_text == "task: question answering | query: 期限は？"
    assert document_text == "title: none | text: 提出期限は14日以内。"
    assert calls[0]["config"].output_dimensionality == 768
    assert embedder.request_count == 2
