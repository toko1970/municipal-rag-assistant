from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def test_streamlit_question_references_and_feedback_flow() -> None:
    fixture_image = (
        Path(__file__).resolve().parents[1]
        / "eval/visual_fixtures/images/flowchart_dev_001_page_001.png"
    )
    result = {
        "request_id": "00000000-0000-0000-0000-000000000001",
        "question": "給与支給日はいつですか？",
        "answer": "回答分類: 根拠十分\n\n回答:\n- 毎月21日です。",
        "references": [
            {
                "document_id": "DOC-001",
                "document_name": "給与制度規程",
                "heading": "給与支給日",
                "chunk_id": "element-1",
                "content": "職員の給与は毎月21日に支給する。",
                "version_id": "version-001",
                "version": "1.0",
                "effective_date": "2025-04-01",
                "document_role": "primary",
                "is_primary": True,
                "content_hash": "a" * 64,
                "score": 0.9,
                "source": "01_salary_rules.md",
                "visual_asset": {
                    "content": fixture_image.read_bytes(),
                    "page_number": 1,
                },
            }
        ],
    }
    with (
        patch("src.rag_chain.generate_answer", return_value=result) as generate,
        patch("src.feedback.save_feedback") as save_feedback,
    ):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        app.text_area[0].set_value("給与支給日はいつですか？")
        app.button[0].click().run()

        assert not app.exception
        assert any("回答を生成しました" in item.value for item in app.success)
        assert any("回答分類: 根拠十分" in item.value for item in app.markdown)
        assert app.expander[0].label == "参照 1: 給与制度規程 / 給与支給日"
        displayed_text = " ".join(
            item.value for item in [*app.text, *app.markdown]
        )
        assert "version-001" in displayed_text
        assert "2025-04-01" in displayed_text
        assert "職員の給与は毎月21日に支給する。" in displayed_text
        generate.assert_called_once_with("給与支給日はいつですか？")

        app.radio[0].set_value("修正して採用した")
        app.text_area[1].set_value("表現を修正")
        app.button[1].click().run()

        assert not app.exception
        assert any("フィードバックを保存しました" in item.value for item in app.success)
        save_feedback.assert_called_once_with(
            result=result,
            feedback="修正して採用した",
            comment="表現を修正",
        )


def test_incomplete_generation_is_warning_without_success_label() -> None:
    result = {
        "request_id": "00000000-0000-0000-0000-000000000002",
        "question": "適用単価は？",
        "answer": "回答の内容を十分に確認できませんでした。",
        "answer_status": "GENERATION_INCOMPLETE",
        "answer_label": None,
        "claims": [],
        "references": [],
    }
    with patch("src.rag_chain.generate_answer", return_value=result):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        app.text_area[0].set_value(result["question"])
        app.button[0].click().run()
        assert not app.exception
        assert app.warning
        assert not any("回答を生成しました" in item.value for item in app.success)
        assert not any("根拠十分" in item.value for item in app.markdown)


def test_failed_new_question_does_not_keep_previous_answer() -> None:
    first = {
        "question": "質問A",
        "answer": "回答A",
        "references": [],
    }
    with (
        patch("src.rag_chain.generate_answer", side_effect=[first, RuntimeError("failed")]),
        patch("src.feedback.save_feedback"),
    ):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        app.text_area[0].set_value("質問A")
        app.button[0].click().run()
        assert any("回答A" in item.value for item in app.markdown)

        app.text_area[0].set_value("質問B")
        app.button[0].click().run()
        assert not any("回答A" in item.value for item in app.markdown)
        assert not any("回答結果" in item.value for item in app.subheader)


def test_missing_reference_version_metadata_is_not_invented() -> None:
    result = {
        "question": "質問",
        "answer": "回答",
        "references": [
            {
                "document_id": "DOC-002",
                "document_name": "通知",
                "heading": "対象",
                "chunk_id": "element-2",
                "content": "根拠本文",
                "source": "02_notice.md",
                "score": 0.8,
            }
        ],
    }
    with patch("src.rag_chain.generate_answer", return_value=result):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        app.text_area[0].set_value("質問")
        app.button[0].click().run()

        shown = " ".join(item.value for item in app.markdown)
        assert not app.exception
        assert "施行日" not in shown
        assert "文書版" not in shown
        assert "文書の役割" not in shown
        assert "02_notice.md" in shown
