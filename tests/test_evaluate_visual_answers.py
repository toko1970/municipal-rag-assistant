import json
from pathlib import Path
from uuid import uuid4

import pytest

from eval.evaluate_visual_answers import (
    DEFAULT_FIXTURE_MANIFEST,
    evaluate_visual_answers,
    prepare_visual_corpus,
    token_cost_usd,
)


def dataset() -> dict:
    return {
        "dataset_version": "test-v1",
        "split": "development",
        "scenarios": [
            {
                "scenario_id": "VD001",
                "question": "質問",
                "difficulty": "direct",
                "expected_classification": "grounded",
                "fixture_ids": ["fixture-1"],
                "expected_answer_key": "答え",
                "required_evidence": [{"element_ref": "node:one"}],
            }
        ],
    }


def test_evaluation_records_classification_retrieval_usage_and_review(tmp_path) -> None:
    def generate(_question: str) -> dict:
        return {
            "answer": "回答分類: 根拠十分\n\n回答:\n- 答え",
            "answer_label": "根拠十分",
            "claims": [{"claim_id": "claim-1", "evidence_element_ids": [uuid4()]}],
            "references": [{"element_id": "element-1"}],
            "generation": {"input_tokens": 100, "output_tokens": 10},
            "classification": {"input_tokens": 50, "output_tokens": 5},
            "classification_decision_version": "classification-decision-v2",
            "_evaluation_classification_factors": {
                "retrieval_sufficient": True,
                "answer_fully_supported": True,
            },
        }

    summary = evaluate_visual_answers(
        dataset=dataset(),
        output_dir=tmp_path / "run",
        generate_fn=generate,
        fixture_by_element={"element-1": "fixture-1"},
        max_scenarios=1,
        max_cost_usd=0.25,
    )

    assert summary["classification_correct"] == 1
    assert summary["required_fixture_retrieved"] == 1
    assert summary["content_review_pending"] == 1
    assert summary["estimated_cost_usd"] == token_cost_usd(150, 15)
    row = json.loads((tmp_path / "run/records.jsonl").read_text())
    assert row["content_review_status"] == "pending"
    assert row["classification_decision_version"] == "classification-decision-v2"
    assert row["classification_factors"]["retrieval_sufficient"] is True
    assert isinstance(row["claims"][0]["evidence_element_ids"][0], str)


def test_evaluation_never_overwrites_prior_run(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    with pytest.raises(FileExistsError):
        evaluate_visual_answers(
            dataset=dataset(),
            output_dir=output,
            generate_fn=lambda _question: {},
            fixture_by_element={},
            max_scenarios=1,
            max_cost_usd=0.25,
        )


def test_evaluation_resume_does_not_repeat_completed_scenario(tmp_path) -> None:
    calls = []

    def generate(_question: str) -> dict:
        calls.append(1)
        return {
            "answer": "回答",
            "answer_label": "根拠十分",
            "references": [{"element_id": "element-1"}],
            "generation": {"input_tokens": 10, "output_tokens": 1},
            "classification": {"input_tokens": 10, "output_tokens": 1},
        }

    kwargs = {
        "dataset": dataset(),
        "output_dir": tmp_path / "run",
        "generate_fn": generate,
        "fixture_by_element": {"element-1": "fixture-1"},
        "max_scenarios": 1,
        "max_cost_usd": 0.25,
    }
    evaluate_visual_answers(**kwargs)
    evaluate_visual_answers(**kwargs, resume=True)

    assert len(calls) == 1


def test_prepared_corpus_contains_all_six_visual_fixtures(tmp_path) -> None:
    class Embeddings:
        def embed_documents(self, texts, task_type):
            assert task_type == "RETRIEVAL_DOCUMENT"
            return [[float(index + 1), 1.0] for index, _text in enumerate(texts)]

    corpus = prepare_visual_corpus(
        DEFAULT_FIXTURE_MANIFEST, tmp_path / "assets", Embeddings()
    )

    assert len(corpus.assets) == 6
    assert len(corpus.fixture_by_element) == 6
    assert len(corpus.index.list_point_ids()) == 6


def test_evaluation_stops_before_cost_reserve_would_exceed_cap(tmp_path) -> None:
    calls = []

    summary = evaluate_visual_answers(
        dataset=dataset(),
        output_dir=tmp_path / "run",
        generate_fn=lambda _question: calls.append(1),
        fixture_by_element={},
        max_scenarios=1,
        max_cost_usd=0.005,
        per_scenario_cost_reserve_usd=0.01,
    )

    assert not calls
    assert summary["stop_reason"] == "COST_LIMIT_REACHED"
