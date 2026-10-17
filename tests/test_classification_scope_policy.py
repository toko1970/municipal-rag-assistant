import copy
import json

from eval.evaluate_classification_scope_policy import build_cases, make_tasks, score, summarize
from src.classification_scope_policy import build_scope_classification_prompt_from_payload
from src.query_service import build_classification_prompt_v1_from_payload


def output(**overrides):
    factors = dict(retrieval_sufficient=True, answer_fully_supported=True,
                   requires_case_facts=False, requires_policy_judgment=False, version_conflict=False)
    factors.update(overrides)
    return dict(schema_version="1.0", status="SUCCESS", factors=factors, confidence=1.0, error_code=None)


def test_policy_preserves_payload_and_does_not_use_gold():
    cases = build_cases()
    original = copy.deepcopy(cases)
    for case in cases:
        p = case["payload"]
        base = build_classification_prompt_v1_from_payload(p["question"], p["retrieved_evidence"], p["generated_answer"])
        candidate = build_scope_classification_prompt_from_payload(p["question"], p["retrieved_evidence"], p["generated_answer"])
        assert candidate.endswith(base)
        assert json.loads(candidate.split("判定対象: ", 1)[1]) == p
        assert set(p) == {"question", "retrieved_evidence", "generated_answer"}
    assert cases == original


def test_frozen_tasks_pair_every_input_and_exclude_ambiguous_gold():
    cases = build_cases()
    tasks = make_tasks(cases)
    assert len(cases) == 24 and len(tasks) == 56
    assert not ({"A01", "B01"} & {c["scenario_id"] for c in cases})
    for t in tasks:
        matches = [x for x in tasks if x["case_id"] == t["case_id"] and x["repetition"] == t["repetition"]]
        assert {x["arm"] for x in matches} == {"baseline", "candidate"}
        assert len(matches) == 2


def test_score_validates_display_instead_of_label_only():
    case = next(c for c in build_cases() if c["id"] == "C01-formal")
    assert score(case, output())["correct"]
    altered = copy.deepcopy(case)
    altered["payload"]["generated_answer"]["missing_conditions"] = ["未確認条件"]
    result = score(altered, output())
    assert result["label"] == "根拠十分"
    assert not result["correct"]
    assert result["display_error"] == "DisplayContractError"


def test_true_individual_review_is_not_counted_as_success_when_relaxed():
    case = next(c for c in build_cases() if c["id"] == "A03-formal")
    assert score(case, output(requires_case_facts=True))["correct"]
    result = score(case, output())
    assert not result["correct"] and result["unsafe_sufficient"]


def test_generation_failures_are_diagnostic_not_document_gold():
    for case in build_cases():
        if case["id"] in {"D03", "D04"}:
            assert case["expected_label"] is None
            assert score(case, output(answer_fully_supported=False))["correct"]
            assert not score(case, output())["correct"]


def test_incomplete_runs_cannot_pass():
    cases = build_cases()
    tasks = make_tasks(cases)
    summary = summarize(cases, tasks, [], "FAIL_FAST_ERROR", 0)
    assert not summary["complete_without_errors"]
    assert not summary["gate1_pass"]
