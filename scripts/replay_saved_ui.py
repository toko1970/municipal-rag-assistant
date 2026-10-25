"""Replay two public saved development responses through the unchanged app UI.

Run: streamlit run scripts/replay_saved_ui.py
No model, embedding, database, or feedback write is executed by this entry point.
This is a documentation replay, not a live quality evaluation.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ANSWER_SOURCE = ROOT / "eval/results/model_gemini_gemini-3.1-flash-lite_formal.csv"
RETRIEVAL_SOURCE = ROOT / "eval/results/model_evaluation_retrieval.jsonl"
CASE_IDS = ("Q011", "Q076")


def load_saved_cases() -> dict[str, dict]:
    """Join only the selected public records; never infer missing version fields."""
    with ANSWER_SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = {
            row["question_id"]: row
            for row in csv.DictReader(stream)
            if row["question_id"] in CASE_IDS
        }
    retrieval = {}
    with RETRIEVAL_SOURCE.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["question_id"] in CASE_IDS:
                retrieval[row["question_id"]] = row
    if set(rows) != set(CASE_IDS) or set(retrieval) != set(CASE_IDS):
        raise ValueError("Required public saved response is missing")
    cases = {}
    for case_id in CASE_IDS:
        row, cached = rows[case_id], retrieval[case_id]
        if row["generation_error"] or cached["retrieval_error"]:
            raise ValueError("Saved response contains an execution error")
        if row["question"] != cached["question"]:
            raise ValueError("Saved question and retrieval do not match")
        sections = cached["context"].split("\n文書名: ")[1:]
        if len(sections) != len(cached["references"]):
            raise ValueError("Cannot associate saved context with references")
        references = []
        for ref, section in zip(cached["references"], sections, strict=True):
            header, content = section.split("\n\n本文:\n", 1)
            name, heading = header.split("\n見出し: ", 1)
            if name != ref["document_name"] or heading != (ref["heading"] or ""):
                raise ValueError("Saved reference order does not match context")
            references.append({**ref, "content": content.rstrip("\n")})
        cases[case_id] = {
            "question": row["question"],
            "answer": row["answer"].replace("\\n", "\n"),
            "answer_label": row["predicted_answer_type"],
            "references": references,
        }
    return cases


def main() -> None:
    sys.path.insert(0, str(ROOT))
    import streamlit as st
    from src import feedback, rag_chain

    cases = load_saved_cases()
    by_question = {case["question"]: case for case in cases.values()}

    def replay(question: str) -> dict:
        if question.strip() not in by_question:
            raise ValueError("Replay supports only the two documented questions")
        return by_question[question.strip()]

    def no_feedback_write(*args, **kwargs) -> None:
        st.info("保存応答の再生画面ではフィードバックを保存しません。")
        st.stop()

    original_config = st.set_page_config

    def replay_page_config(**kwargs) -> None:
        original_config(**kwargs)
        st.caption(
            "保存応答の再生 ｜ 2026-09-23のFlash-Lite評価応答を現行UIに表示 ｜ "
            "新規LLM生成・DB接続なし"
        )

    with (
        patch.object(rag_chain, "generate_answer", side_effect=replay),
        patch.object(feedback, "save_feedback", side_effect=no_feedback_write),
        patch.object(st, "set_page_config", side_effect=replay_page_config),
    ):
        runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
    st.caption("再生できる質問: " + " ／ ".join(by_question))


if __name__ == "__main__":
    main()
