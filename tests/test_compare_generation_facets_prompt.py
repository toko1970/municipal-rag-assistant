from eval.compare_generation_facets_prompt import (
    build_required_facets_prompt,
    score_record,
)


def test_required_facets_prompt_adds_rules_without_changing_schema_request() -> None:
    prompt = build_required_facets_prompt("期限は？", [])

    assert "必須項目" in prompt
    assert "質問の必須項目に対応しない関連情報" in prompt
    assert "answer-output-v1のJSONだけ" in prompt


def test_score_record_requires_label_facets_and_no_forbidden_claim() -> None:
    record = {
        "expected_label": "判断要",
        "predicted_label": "判断要",
        "answer": "翌月以降。個別確認が必要。",
        "claims": [],
        "missing_conditions": ["反映月の確認"],
        "error": None,
    }
    rule = {
        "required_patterns": ["翌月以降", "確認"],
        "forbidden_patterns": ["受付不可"],
    }

    score = score_record(record, rule)

    assert score["overall_success"] is True


def test_score_record_rejects_question_external_claim() -> None:
    record = {
        "expected_label": "判断要",
        "predicted_label": "判断要",
        "answer": "届出は受け付けます。不備がある場合は受け付けられません。確認が必要。",
        "claims": [],
        "missing_conditions": [],
        "error": None,
    }
    rule = {
        "required_patterns": ["受け付け", "確認"],
        "forbidden_patterns": ["不備.{0,12}受け付けられません"],
    }

    score = score_record(record, rule)

    assert score["forbidden_claims_ok"] is False
    assert score["overall_success"] is False
