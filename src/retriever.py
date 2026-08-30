from functools import lru_cache

from config import TOP_K
from src.vector_store import load_or_create_vector_store


@lru_cache(maxsize=1)
def get_vector_store():
    """同一プロセス内でベクトルDBを再利用する。"""

    return load_or_create_vector_store()


def retrieve_documents_with_score(query: str, top_k: int = TOP_K):
    """
    質問文に関連するチャンクをスコア付きで検索する。
    """

    vector_store = get_vector_store()

    results = vector_store.similarity_search_with_score(
        query=query,
        k=top_k,
    )

    return results

# if __name__ == "__main__":
#     query = "給与支給日はいつですか？"

#     docs = retrieve_documents_with_score(query)

#     print(f"質問: {query}")
#     print(f"検索結果数: {len(docs)}")

#     for i, (doc, score) in enumerate(docs, start=1):
#         print("=" * 60)
#         print(f"検索順位: {i}")
#         print(f"スコア: {score}")

#         print("metadata:")
#         print(doc.metadata)

#         print("content:")
#         print(doc.page_content[:500])
