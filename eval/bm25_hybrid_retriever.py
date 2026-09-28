"""Local Sudachi BM25 and reciprocal-rank fusion for an isolated experiment."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from sudachipy import Dictionary, SplitMode

from src.contracts import IndexableElement, SearchHit
from src.embedding_representation import contextual_heading_document_text


BM25_K1 = 1.2
BM25_B = 0.75
RRF_K = 60
DENSE_CANDIDATE_K = 20
SPARSE_CANDIDATE_K = 20


def create_sudachi_tokenizer() -> Callable[[str], list[str]]:
    tokenizer = Dictionary().tokenizer(mode=SplitMode.C)

    def tokenize(text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKC", text).lower()
        return [
            morpheme.normalized_form()
            for morpheme in tokenizer.tokenize(normalized)
            if re.search(r"[\w一-龯ぁ-んァ-ヶ]", morpheme.surface())
        ]

    return tokenize


@dataclass(frozen=True)
class BM25Hit:
    element: IndexableElement
    score: float
    rank: int


class BM25Index:
    def __init__(
        self,
        elements: list[IndexableElement],
        *,
        tokenize: Callable[[str], list[str]],
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> None:
        if not elements:
            raise ValueError("BM25 corpusが空です")
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 parameterが不正です")
        self.elements = elements
        self.tokenize = tokenize
        self.k1 = k1
        self.b = b
        self.term_frequencies = [
            Counter(tokenize(contextual_heading_document_text(element)))
            for element in elements
        ]
        self.document_lengths = [sum(terms.values()) for terms in self.term_frequencies]
        self.average_document_length = sum(self.document_lengths) / len(elements)
        document_frequency = Counter(
            term for terms in self.term_frequencies for term in terms
        )
        corpus_size = len(elements)
        self.idf = {
            term: math.log(1 + (corpus_size - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, limit: int) -> list[BM25Hit]:
        if limit < 1:
            raise ValueError("limitは1以上で指定してください")
        query_terms = Counter(self.tokenize(query))
        scored = []
        for element, frequencies, length in zip(
            self.elements,
            self.term_frequencies,
            self.document_lengths,
            strict=True,
        ):
            score = 0.0
            for term, query_frequency in query_terms.items():
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / self.average_document_length
                )
                score += (
                    self.idf.get(term, 0.0)
                    * frequency
                    * (self.k1 + 1)
                    / denominator
                    * query_frequency
                )
            if score > 0:
                scored.append((element, score))
        scored.sort(key=lambda item: (-item[1], str(item[0].id)))
        return [
            BM25Hit(element=element, score=score, rank=rank)
            for rank, (element, score) in enumerate(scored[:limit], start=1)
        ]


def reciprocal_rank_fusion(
    dense_hits: list[SearchHit], sparse_hits: list[BM25Hit], *, limit: int, rrf_k: int
) -> list[SearchHit]:
    if limit < 1 or rrf_k < 1:
        raise ValueError("limitとrrf_kは1以上で指定してください")
    elements = {hit.element.id: hit.element for hit in [*dense_hits, *sparse_hits]}
    dense_ranks = {hit.element.id: hit.rank for hit in dense_hits}
    sparse_ranks = {hit.element.id: hit.rank for hit in sparse_hits}
    fused = []
    for element_id, element in elements.items():
        score = 0.0
        if element_id in dense_ranks:
            score += 1 / (rrf_k + dense_ranks[element_id])
        if element_id in sparse_ranks:
            score += 1 / (rrf_k + sparse_ranks[element_id])
        fused.append((element, score, dense_ranks.get(element_id, 10**9)))
    fused.sort(key=lambda item: (-item[1], item[2], str(item[0].id)))
    return [
        SearchHit(element=element, score=score, rank=rank)
        for rank, (element, score, _dense_rank) in enumerate(fused[:limit], start=1)
    ]
