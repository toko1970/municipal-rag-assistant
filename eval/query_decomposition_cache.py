"""Read an audited subset from a previously fixed subquery-vector cache."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from eval.embedding_profiles import EmbeddingProfile


def load_cached_subquery_vectors(
    path: Path,
    *,
    profile: EmbeddingProfile,
    kind: str,
    ids: list[str],
) -> list[list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    conditions = payload.get("conditions", {})
    if conditions.get("profile") != asdict(profile) or conditions.get("kind") != kind:
        raise ValueError(f"Embedding cacheのprofileまたはkindが一致しません: {path}")
    cached_ids = conditions.get("ids", [])
    vectors = payload.get("vectors", [])
    if len(cached_ids) != len(vectors) or len(cached_ids) != len(set(cached_ids)):
        raise ValueError(f"Embedding cacheのIDとvectorが不正です: {path}")
    by_id = dict(zip(cached_ids, vectors, strict=True))
    missing = [item for item in ids if item not in by_id]
    if missing:
        raise ValueError(f"Embedding cacheに必要なsubqueryがありません: {missing}")
    return [by_id[item] for item in ids]
