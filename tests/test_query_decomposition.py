from types import SimpleNamespace

from src.query_decomposition import (
    DecomposedVectorIndex,
    decompose_query,
    retrieve_decomposed,
)
from src.contracts import SearchHit


def _hit(element_id: str, rank: int) -> SearchHit:
    element = SimpleNamespace(id=element_id)
    return SearchHit(element=element, score=1 / rank, rank=rank)


def test_decomposes_supported_multi_intent_questions_without_gold() -> None:
    assert decompose_query(
        "転居後に通勤しなくなった職員の通勤手当はどうしますか？"
    ) == [
        "転居 通勤しなくなった 通勤手当 支給停止",
        "転居 住所変更届 提出が必要な場合 提出期限",
    ]
    assert decompose_query(
        "2025年10月の出生について支給開始時期と届出期限をまとめてください。"
    ) == [
        "2025年10月 出生 扶養手当 支給開始時期",
        "2025年10月 出生 扶養親族変更届 提出期限",
    ]


def test_leaves_single_intent_question_unchanged() -> None:
    question = "給与制度規程は常勤職員に適用されますか？"
    assert decompose_query(question) == [question]


def test_leaves_unproven_decomposition_rules_unchanged() -> None:
    questions = (
        "2025年10月に通勤経路が変わり、1.8kmを車通勤する職員の要件と届出期限を教えてください。",
        "過払給与の返納方法と給与口座変更に必要な書類をまとめてください。",
        "2025年10月に本人名義で契約し、家賃15,500円を負担する住宅へ入居した場合の要件・書類・期限は？",
    )

    for question in questions:
        assert decompose_query(question) == [question]


def test_balances_subquery_results_and_removes_duplicates() -> None:
    question = "転居で通勤しなくなった場合、通勤手当と住所変更届をどう処理しますか？"
    first, second = decompose_query(question)
    responses = {
        first: [_hit("A", 1), _hit("B", 2), _hit("C", 3)],
        second: [_hit("A", 1), _hit("D", 2), _hit("E", 3)],
        question: [_hit("F", 1), _hit("G", 2)],
    }

    result = retrieve_decomposed(
        question,
        top_k=5,
        search=lambda query, limit: responses[query][:limit],
    )

    assert [hit.element.id for hit in result] == ["A", "B", "C", "D", "E"]
    assert [hit.rank for hit in result] == [1, 2, 3, 4, 5]


def test_vector_index_embeds_only_added_subqueries() -> None:
    question = "転居で通勤しなくなった場合、通勤手当と住所変更届をどう処理しますか？"
    first, second = decompose_query(question)
    vectors = {first: [1.0], second: [2.0]}
    embedded = []

    class BaseIndex:
        def search(self, vector, limit):
            prefix = "A" if vector == [1.0] else "B" if vector == [2.0] else "Q"
            return [_hit(f"{prefix}{index}", index) for index in range(1, limit + 1)]

    index = DecomposedVectorIndex(
        question=question,
        base_index=BaseIndex(),
        embed_query=lambda query: embedded.append(query) or vectors[query],
    )

    result = index.search([9.0], limit=4)

    assert embedded == [first, second]
    assert [hit.element.id for hit in result] == ["A1", "A2", "B1", "B2"]


def test_vector_index_preserves_single_query_path() -> None:
    question = "給与制度規程は常勤職員に適用されますか？"

    class BaseIndex:
        def search(self, vector, limit):
            assert vector == [9.0]
            return [_hit("A", 1)][:limit]

    index = DecomposedVectorIndex(
        question=question,
        base_index=BaseIndex(),
        embed_query=lambda _query: (_ for _ in ()).throw(AssertionError()),
    )

    assert [hit.element.id for hit in index.search([9.0], 1)] == ["A"]
