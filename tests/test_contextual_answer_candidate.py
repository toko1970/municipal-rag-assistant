import json
from pathlib import Path

import pytest

from eval.evaluate_contextual_answer_candidate import (
    changed_evidence_at_5_ids,
    content_key_ok,
    load_criteria,
)


def test_selects_only_questions_whose_evidence_hit_at_5_changed(tmp_path: Path) -> None:
    fields = "question_id,evidence_hit_at_5\nQ1,0\nQ2,1\nQ3,1\n"
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    baseline.write_text(fields, encoding="utf-8")
    candidate.write_text(
        "question_id,evidence_hit_at_5\nQ1,1\nQ2,1\nQ3,0\n", encoding="utf-8"
    )

    assert changed_evidence_at_5_ids(baseline, candidate) == ["Q1", "Q3"]


def test_content_key_requires_all_patterns_and_order() -> None:
    rule = {
        "required_patterns": ["受付", "支給額", "システム.*登録"],
        "ordered_patterns": ["受付", "支給額", "システム.*登録"],
    }

    assert content_key_ok("受付後、支給額を確認し、システムへ登録する。", rule)
    assert not content_key_ok("受付後、システム登録し、支給額を確認する。", rule)
    assert not content_key_ok("受付後、支給額を確認する。", rule)


def test_content_key_can_accept_fixed_spelling_variants() -> None:
    rule = {
        "required_patterns": ["(受付|受け付け)", "口座情報"],
        "ordered_patterns": ["(受付|受け付け)", "口座情報"],
    }

    assert content_key_ok("届を受け付けた後、口座情報を確認する。", rule)


def test_criteria_must_be_fixed_for_exact_target_set(tmp_path: Path) -> None:
    path = tmp_path / "criteria.json"
    path.write_text(
        json.dumps(
            {"Q1": {"required_patterns": ["10日"], "ordered_patterns": []}}
        ),
        encoding="utf-8",
    )

    assert set(load_criteria(path, ["Q1"])) == {"Q1"}
    with pytest.raises(ValueError, match="質問ID"):
        load_criteria(path, ["Q1", "Q2"])
