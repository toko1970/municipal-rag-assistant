from eval.run_local_nli_classifier_pilot import (
    FACTOR_HYPOTHESES,
    audit_token_lengths,
    build_premise,
)


class WordTokenizer:
    model_max_length = 8

    def __call__(
        self,
        text: str,
        text_pair: str,
        *,
        add_special_tokens: bool,
        truncation: bool,
    ) -> dict:
        assert add_special_tokens is True
        assert truncation is False
        return {"input_ids": list(range(len((text + " " + text_pair).split()) + 3))}


def case() -> dict:
    return {
        "case_id": "C01",
        "question": "この条件を満たしますか？",
        "evidence": [{"element_id": "e1", "content": "条件は10以上です。"}],
        "generated_answer": {
            "claims": [{"claim_id": "claim-1", "text": "10なら満たします。"}],
            "missing_conditions": ["対象日の確認"],
        },
    }


def test_build_premise_contains_every_classification_input() -> None:
    premise = build_premise(case())

    assert "この条件を満たしますか？" in premise
    assert "[e1] 条件は10以上です。" in premise
    assert "[claim-1] 10なら満たします。" in premise
    assert "対象日の確認" in premise
    assert premise == build_premise(case())


def test_audit_marks_over_limit_without_truncation() -> None:
    result = audit_token_lengths(
        {"cases": [case()]}, WordTokenizer(), max_tokens=8
    )

    assert result["pair_count"] == len(FACTOR_HYPOTHESES)
    assert result["over_limit_pair_count"] == len(FACTOR_HYPOTHESES)
    assert result["over_limit_case_count"] == 1
    assert all(record["exceeds_limit"] for record in result["records"])
