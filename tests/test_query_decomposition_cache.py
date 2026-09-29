import json
from dataclasses import asdict

import pytest

from eval.embedding_profiles import PROFILES
from eval.query_decomposition_cache import load_cached_subquery_vectors


def test_loads_requested_vectors_from_a_larger_fixed_cache(tmp_path) -> None:
    profile = PROFILES["gemini-embedding-001"]
    path = tmp_path / "vectors.json"
    path.write_text(
        json.dumps(
            {
                "conditions": {
                    "profile": asdict(profile),
                    "kind": "query-decomposition-v1",
                    "ids": ["a", "b", "c"],
                },
                "vectors": [[1.0], [2.0], [3.0]],
            }
        ),
        encoding="utf-8",
    )

    assert load_cached_subquery_vectors(
        path,
        profile=profile,
        kind="query-decomposition-v1",
        ids=["c", "a"],
    ) == [[3.0], [1.0]]


def test_rejects_a_missing_requested_subquery(tmp_path) -> None:
    profile = PROFILES["gemini-embedding-001"]
    path = tmp_path / "vectors.json"
    path.write_text(
        json.dumps(
            {
                "conditions": {
                    "profile": asdict(profile),
                    "kind": "query-decomposition-v1",
                    "ids": ["a"],
                },
                "vectors": [[1.0]],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="必要なsubquery"):
        load_cached_subquery_vectors(
            path,
            profile=profile,
            kind="query-decomposition-v1",
            ids=["b"],
        )
