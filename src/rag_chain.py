from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from config import GOOGLE_API_KEY, LLM_MODEL_NAME
from src.retriever import retrieve_documents_with_score
from src.logger import save_rag_log


def build_context(results) -> str:
    """
    Retrieverの検索結果から、LLMへ渡すコンテキストを生成する。
    """

    contexts = []

    for doc, score in results:
        context = f"""
文書名: {doc.metadata.get("document_name", "")}
見出し: {doc.metadata.get("見出し2", "")}

本文:
{doc.page_content}
"""
        contexts.append(context)

    return "\n\n".join(contexts)


def build_references(results) -> list[dict]:
    """
    Retrieverの検索結果から、参照チャンク情報を作成する。
    """

    references = []

    for doc, score in results:
        references.append(
            {
                "document_id": doc.metadata.get("document_id"),
                "document_name": doc.metadata.get("document_name"),
                "heading": doc.metadata.get("見出し2"),
                "chunk_id": doc.metadata.get("chunk_id"),
                "score": round(score, 4),
                "source": doc.metadata.get("source"),
            }
        )

    return references


def build_prompt(question: str, context: str) -> str:
    """
    LLMに渡すプロンプトを作成する。
    """

    prompt = f"""
あなたは自治体の人事給与制度に関する問い合わせ支援AIです。

以下のルールを守って回答してください。

【回答分類】

1. 根拠十分
文書に明確な記載がある場合。

2. 判断要
関連文書はあるが、個別事情や制度解釈により断定できない場合。

3. 文書不足
参照文書に質問への回答根拠が確認できない場合。

【重要ルール】

・参照文書に基づいて回答してください。
・参照文書にない内容を推測して回答してはいけません。
・個別判断が必要な場合は、制度所管部署への確認が必要である旨を回答してください。
・根拠文書には、参照した文書名のみを記載してください。
・参照チャンクの本文は出力しないでください。

【参考文書】

{context}

【質問】

{question}

以下の形式で回答してください。

回答分類:
（根拠十分 / 判断要 / 文書不足）

回答:

根拠文書:
"""
    return prompt


def generate_answer(question: str) -> dict:
    """
    質問に対して、Retriever検索とLLM回答生成を行う。
    """

    results = retrieve_documents_with_score(question)

    context = build_context(results)

    prompt = build_prompt(
        question=question,
        context=context,
    )

    llm = ChatGoogleGenerativeAI(
        model=LLM_MODEL_NAME,
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
    )

    response = llm.invoke(
        [HumanMessage(content=prompt)]
    )

    result = {
        "question": question,
        "answer": response.content,
        "retrieved_documents": results,
        "references": build_references(results),
    }

    save_rag_log(result)

    return result


# if __name__ == "__main__":
#     test_questions = [
#         "給与支給日はいつですか？",
#         "別居している父母を扶養親族として認定できますか？",
#         "退職手当の計算方法を教えてください。",
#     ]

#     for question in test_questions:
#         print("=" * 80)
#         print(f"質問: {question}")
#         print("=" * 80)

#         result = generate_answer(question)

#         save_feedback(
#             result=result,
#             feedback="採用した",
#             comment="テスト保存",
#         )

#         print(result["answer"])

#         print("\n参照チャンク:")
#         for ref in result["references"]:
#             print(
#                 f"- {ref['document_name']} > {ref['heading']} "
#                 f"(chunk_id={ref['chunk_id']}, score={ref['score']})"
#             )

#         print()
