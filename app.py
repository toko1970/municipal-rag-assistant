import streamlit as st

from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from src.rag_chain import generate_answer
from src.feedback import save_feedback, VALID_FEEDBACK_VALUES
from src.provider_retry import classify_provider_error, run_with_503_backoff


st.set_page_config(
    page_title="自治体向け制度問い合わせ支援RAG",
    page_icon="📘",
    layout="wide",
)

st.title("📘 自治体向け制度問い合わせ支援RAG")
st.caption("人事・給与制度関連文書に基づいて回答します。")
st.info(
    "本アプリはポートフォリオ用のデモです。"
    "検索対象には架空の制度文書を使用しています。"
)


if "result" not in st.session_state:
    st.session_state.result = None


st.subheader("質問入力")

question = st.text_area(
    "制度に関する質問を入力してください",
    placeholder="例：給与支給日はいつですか？",
    height=120,
    max_chars=500,
)

if "is_generating" not in st.session_state:
    st.session_state.is_generating = False

generate_button = st.button(
    "回答を生成する",
    type="primary",
    disabled=st.session_state.is_generating,
)

if generate_button:
    if not question.strip():
        st.warning("質問を入力してください。")
    else:
        st.session_state.result = None
        st.session_state.pop("feedback_value", None)
        st.session_state.pop("feedback_comment", None)
        st.session_state.is_generating = True

        try:
            with st.spinner("回答を生成しています..."):
                result, _provider_503_retries = run_with_503_backoff(
                    lambda: generate_answer(question)
                )

            st.session_state.result = result
            if result.get("degraded") or result.get("answer_status", "SUCCESS") != "SUCCESS":
                st.warning("回答の処理が完了しませんでした。下の案内をご確認ください。")
            else:
                st.success("回答を生成しました。")

        except ChatGoogleGenerativeAIError as error:
            st.session_state.result = None
            error_kind = classify_provider_error(error)
            if error_kind == "rate_limit":
                st.error(
                    "Gemini APIの利用上限に達しました。"
                    "時間を置いて再実行してください。"
                )
            elif error_kind == "unavailable":
                st.error(
                    "Gemini APIが一時的に混雑しています。"
                    "時間を置いて再実行してください。"
                )
            else:
                st.error(
                    "Gemini APIとの通信中にエラーが発生しました。"
                    "時間を置いて再実行してください。"
                )

        except Exception:
            st.session_state.result = None
            st.error("回答の生成中にエラーが発生しました。時間を置いて再実行してください。")
        
        finally:
            st.session_state.is_generating = False

if st.session_state.result is not None:
    result = st.session_state.result

    st.divider()
    st.subheader("回答結果")

    st.caption(f"質問: {result.get('question', '質問を確認できません')}")

    with st.container(border=True):
        st.markdown(result["answer"])

    st.divider()
    st.subheader("参照チャンク")

    references = result.get("references", [])

    if not references:
        st.info("参照チャンクはありません。")
    else:
        for i, ref in enumerate(references, start=1):
            document_name = ref.get("document_name", "不明な文書")
            heading = ref.get("heading", "")
            chunk_id = ref.get("chunk_id", "")
            score = ref.get("score", "")
            source = ref.get("source", "")

            with st.expander(f"参照 {i}: {document_name} / {heading}"):
                visual_asset = ref.get("visual_asset")
                if visual_asset and visual_asset.get("content"):
                    st.image(
                        visual_asset["content"],
                        caption=(
                            f"{document_name} p.{visual_asset.get('page_number', '?')}"
                        ),
                        width="stretch",
                    )
                st.write(f"**文書ID:** {ref.get('document_id')}")
                st.write(f"**文書名:** {document_name}")
                st.write(f"**版ID:** {ref.get('version_id', '未設定')}")
                if ref.get("version") is not None:
                    st.write(f"**文書版:** {ref['version']}")
                if ref.get("effective_date") is not None:
                    st.write(f"**施行日:** {ref['effective_date']}")
                if ref.get("document_role") is not None:
                    st.write(f"**文書の役割:** {ref['document_role']}")
                if ref.get("is_primary") is not None:
                    st.write(f"**主文書:** {'はい' if ref['is_primary'] else 'いいえ'}")
                st.write(f"**見出し:** {heading}")
                st.write(f"**チャンクID:** {chunk_id}")
                st.write(f"**検索スコア:** {score}")
                st.write(f"**ファイル:** {source}")
                if ref.get("content_hash"):
                    st.code(ref["content_hash"], language=None)
                    st.caption("原文ファイルのSHA-256")
                if ref.get("content"):
                    st.markdown("**根拠本文**")
                    st.text(ref["content"])

    st.divider()
    st.subheader("フィードバック")

    feedback = st.radio(
        "この回答を採用しましたか？",
        VALID_FEEDBACK_VALUES,
        horizontal=True,
        key="feedback_value",
    )

    comment = st.text_area(
        "任意コメント",
        placeholder="例：回答は使えるが、表現を少し修正した。",
        height=100,
        key="feedback_comment",
    )

    if st.button("フィードバックを保存する"):
        save_feedback(
            result=result,
            feedback=feedback,
            comment=comment,
        )

        st.success("フィードバックを保存しました。")
