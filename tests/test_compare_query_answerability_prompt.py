from eval.compare_query_answerability_prompt import build_answerability_alignment_prompt


def test_alignment_prompt_limits_missing_conditions_to_requested_granularity() -> None:
    prompt = build_answerability_alignment_prompt("質問", [], {})

    assert "出来事条件で回答できます" in prompt
    assert "何日以内という粒度を明示" in prompt
    assert "重複して入れない" in prompt
