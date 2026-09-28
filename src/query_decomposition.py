"""Deterministic query decomposition for an isolated retrieval experiment."""

from __future__ import annotations

import math
import re
from collections.abc import Callable

from src.contracts import SearchHit, VectorIndex


def _date_context(question: str) -> str:
    match = re.search(r"\d{4}年\d{1,2}月(?:以降)?", question)
    return f"{match.group(0)} " if match else ""


def decompose_query(question: str) -> list[str]:
    """Split supported municipal payroll multi-intent questions without gold data."""
    date = _date_context(question)

    if "転居" in question and "通勤しなく" in question:
        return [
            f"{date}転居 通勤しなくなった 通勤手当 支給停止".strip(),
            f"{date}転居 住所変更届 提出が必要な場合 提出期限".strip(),
        ]

    if "出生" in question and "支給開始時期" in question and "届出期限" in question:
        return [
            f"{date}出生 扶養手当 支給開始時期".strip(),
            f"{date}出生 扶養親族変更届 提出期限".strip(),
        ]

    return [question]


def retrieve_decomposed(
    question: str,
    *,
    top_k: int,
    search: Callable[[str, int], list[SearchHit]],
) -> list[SearchHit]:
    """Reserve an equal candidate quota per intent, then fill from the full query."""
    subqueries = decompose_query(question)
    if subqueries == [question]:
        return search(question, top_k)

    per_intent = max(1, math.ceil(top_k / len(subqueries)))
    selected: list[SearchHit] = []
    seen = set()

    def append_unique(hit: SearchHit) -> None:
        if hit.element.id not in seen and len(selected) < top_k:
            seen.add(hit.element.id)
            selected.append(hit)

    for subquery in subqueries:
        for hit in search(subquery, per_intent):
            append_unique(hit)
    if len(selected) < top_k:
        for hit in search(question, top_k):
            append_unique(hit)

    return [
        SearchHit(element=hit.element, score=hit.score, rank=rank)
        for rank, hit in enumerate(selected, start=1)
    ]


class DecomposedVectorIndex:
    """Apply decomposition while preserving the existing query-time contract."""

    def __init__(
        self,
        *,
        question: str,
        base_index: VectorIndex,
        embed_query: Callable[[str], list[float]],
    ) -> None:
        self.question = question
        self.base_index = base_index
        self.embed_query = embed_query

    def search(self, query_vector: list[float], limit: int) -> list[SearchHit]:
        def search_query(query: str, query_limit: int) -> list[SearchHit]:
            vector = query_vector if query == self.question else self.embed_query(query)
            return self.base_index.search(vector, query_limit)

        return retrieve_decomposed(
            self.question,
            top_k=limit,
            search=search_query,
        )
