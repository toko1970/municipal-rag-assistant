"""親見出し方式で回答品質を評価するための接続処理。"""

from eval.contextual_retriever import retrieve_documents_with_score
from src.rag_chain import generate_answer


def generate_contextual_answer(question: str) -> dict:
    """評価用Retrieverを使い、公開アプリのログを変更せず回答する。"""
    return generate_answer(
        question,
        retrieve_fn=retrieve_documents_with_score,
        record_log=False,
    )
