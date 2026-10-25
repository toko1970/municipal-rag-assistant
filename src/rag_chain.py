from config import LLM_MODEL_NAME, RAG_BACKEND
from src.llm_provider import GeminiProvider
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


def build_prompt(
    question: str,
    context: str,
    *,
    condition_check_candidate: bool = False,
    concise_condition_check_candidate: bool = False,
    conclusion_gate_candidate: bool = False,
) -> str:
    """
    LLMに渡すプロンプトを作成する。
    """

    if sum((condition_check_candidate, concise_condition_check_candidate, conclusion_gate_candidate)) > 1:
        raise ValueError("プロンプト候補は同時に1つだけ指定できます")
    condition_guidance = ""
    if condition_check_candidate:
        condition_guidance = """
【個別結論を出す前の確認手順】

・まず、質問に明記された事実と、参照文書が個別結論の条件として定める事項を整理してください。
・結論に必要な各事項について、質問で確認できる事実、参照文書で確認できる制度要件、未確認の事項を照合してください。
・質問者に関する必要な事実が未確認なら、個別事案の適用可否や処理結果を確定せず、その事実と質問者または関係担当者への確認項目を示してください。
・結論に必要な制度要件が参照文書に見当たらない、または文書の解釈が必要なら、個別結論を確定せず、根拠の不足または解釈上の確認点と制度所管部署への確認項目を示してください。
・一般的な制度要件は説明できますが、一般要件の説明を個別事案の結論として表現しないでください。
・質問に明記された事実は既知として扱い、それを不明として扱わないでください。
・必要事項が質問と参照文書から確認できる場合は、不要に保留せず、根拠に沿って結論を回答してください。
"""
    elif concise_condition_check_candidate:
        condition_guidance = """
【個別結論の確認と回答】

回答を作る前に、質問に書かれた事実と、根拠文書上の結論に必要な条件を照合してください。質問に明記された事実は確認済みとして扱ってください。
結論を左右する質問者側の事実が不明なら、回答の冒頭で「現時点では個別の可否を確定できません」と明示してください。その事実を確認するまでは、本件が対象になる・ならないという結論を述べないでください。一般要件を説明するときは、条件付きの制度説明であることを明確にしてください。
必要な制度要件が根拠文書にない、または解釈が定まらない場合も個別結論を確定せず、所管部署への確認事項を示してください。
質問と根拠文書から必要条件が揃っている場合は、直接回答してください。不要な条件を追加して保留しないでください。
確認のための内部分析や長いチェックリストは回答に出さず、判断、未確認事項または必須条件、次の確認先を簡潔に伝えてください。
"""
    elif conclusion_gate_candidate:
        condition_guidance = """
【個別結論の許可条件】

個別事案について「対象になる／ならない」「支給される／されない」「受理される／されない」などの結論を書く前に、その結論を左右する質問者側の事実を参照文書上の要件と照合してください。
個別結論を書けるのは、結論に必要な質問者側の事実が質問文で確認でき、かつ判断に必要な制度要件が参照文書に明記されている場合だけです。どちらかが満たされないときは、その個別結論を肯定・否定のいずれにも確定しないでください。
条件が未確認の場合は、未確認の事実を具体的に示し、誰に何を確認すればよいかを案内してください。制度要件や解釈が不足している場合は、その不足点と所管部署への確認事項を示してください。一般的な制度要件は、個別事案への結論と混同しない条件付きの説明として回答できます。
回答分類を「判断要」とする場合、回答本文に個別の可否を断定する文を含めないでください。後段に留保や確認案内を加えても、先に述べた個別結論の断定は取り消されたことになりません。
質問に明記された事実は既知として扱ってください。質問が一般的な制度説明を求めている場合や、質問と根拠文書から必要条件がそろっている場合は、不要な個別確認を求めず直接回答してください。
内部の照合過程は出力せず、回答分類と、結論または未確認事項・確認先を簡潔に示してください。
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

{condition_guidance}

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


def generate_answer(
    question: str,
    retrieve_fn=None,
    record_log: bool = True,
    llm_provider=None,
) -> dict:
    """
    質問に対して、Retriever検索とLLM回答生成を行う。
    """

    if (
        RAG_BACKEND == "qdrant"
        and retrieve_fn is None
        and llm_provider is None
        and record_log
    ):
        from src.rag_v2 import generate_qdrant_answer

        return generate_qdrant_answer(question)
    if RAG_BACKEND not in {"chroma", "qdrant"}:
        raise ValueError(f"未対応のRAG_BACKENDです: {RAG_BACKEND}")

    if retrieve_fn is None:
        retrieve_fn = retrieve_documents_with_score

    results = retrieve_fn(question)

    context = build_context(results)

    prompt = build_prompt(
        question=question,
        context=context,
    )

    if llm_provider is None:
        llm_provider = GeminiProvider(LLM_MODEL_NAME)
    response = llm_provider.generate(prompt)

    result = {
        "question": question,
        "answer": response.text,
        "retrieved_documents": results,
        "references": build_references(results),
        "generation": response.metadata(),
    }

    if record_log:
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
