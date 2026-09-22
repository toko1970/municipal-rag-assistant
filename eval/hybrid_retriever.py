from functools import lru_cache
from collections import Counter
import math
import re
import unicodedata

from config import TOP_K
from src.retriever import get_vector_store

RRF_K = 60
CANDIDATE_K = 30


def character_ngrams(text: str) -> Counter[str]:
    """日本語の分かち書きに依存しない文字2・3-gramを作る。"""
    normalized = re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", text).lower())
    return Counter(
        normalized[index : index + size]
        for size in (2, 3)
        for index in range(len(normalized) - size + 1)
    )


def heading_path(metadata: dict) -> str:
    return " > ".join(
        str(metadata[key])
        for key in ("見出し1", "見出し2", "見出し3")
        if metadata.get(key)
    )


@lru_cache(maxsize=1)
def get_lexical_index() -> tuple[dict, dict, dict]:
    """既存のChromaチャンクから文字列検索用の軽量な索引を作る。"""
    data = get_vector_store().get(include=["documents", "metadatas"])
    term_frequencies = {}
    for metadata, content in zip(data["metadatas"], data["documents"]):
        chunk_id = metadata.get("chunk_id")
        if chunk_id is not None:
            heading = heading_path(metadata)
            term_frequencies[chunk_id] = character_ngrams(
                f"{heading} {heading} {content}"
            )

    document_frequencies = Counter(
        term for terms in term_frequencies.values() for term in terms
    )
    corpus_size = len(term_frequencies)
    idf = {
        term: math.log((corpus_size + 1) / (frequency + 1)) + 1
        for term, frequency in document_frequencies.items()
    }
    norms = {
        chunk_id: math.sqrt(
            sum((frequency * idf[term]) ** 2 for term, frequency in terms.items())
        )
        for chunk_id, terms in term_frequencies.items()
    }
    return term_frequencies, idf, norms


def lexical_scores(query: str, results: list) -> list[float]:
    """候補チャンクと質問の文字ngram TF-IDF cosine類似度を計算する。"""
    term_frequencies, idf, norms = get_lexical_index()
    query_terms = character_ngrams(query)
    query_norm = math.sqrt(
        sum(
            (frequency * idf.get(term, 0)) ** 2
            for term, frequency in query_terms.items()
        )
    )
    scores = []
    for doc, _score in results:
        chunk_id = doc.metadata.get("chunk_id")
        terms = term_frequencies.get(chunk_id, {})
        norm = norms.get(chunk_id, 0)
        if not query_norm or not norm:
            scores.append(0.0)
            continue
        dot_product = sum(
            frequency * terms.get(term, 0) * idf.get(term, 0) ** 2
            for term, frequency in query_terms.items()
        )
        scores.append(dot_product / (query_norm * norm))
    return scores


def retrieve_documents_with_score(query: str, top_k: int = TOP_K):
    """
    ベクトル順位と文字列順位をRRFで統合し、上位チャンクを返す。
    戻り値のscoreは従来どおりChromaの距離であり、統合順位の点数ではない。
    """

    vector_store = get_vector_store()

    results = vector_store.similarity_search_with_score(
        query=query,
        k=max(top_k, CANDIDATE_K),
    )

    if not results:
        return []

    scores = lexical_scores(query, results)
    lexical_order = sorted(
        range(len(results)), key=lambda index: scores[index], reverse=True
    )
    lexical_ranks = {index: rank for rank, index in enumerate(lexical_order, start=1)}
    combined_order = sorted(
        range(len(results)),
        key=lambda index: 1 / (RRF_K + index + 1) + 1 / (RRF_K + lexical_ranks[index]),
        reverse=True,
    )
    return [results[index] for index in combined_order[:top_k]]
