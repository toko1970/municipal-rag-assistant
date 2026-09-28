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
