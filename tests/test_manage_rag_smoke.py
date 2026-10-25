import json
from unittest.mock import patch

import pytest

from scripts import manage_rag_v2
from src.smoke_validation import SMOKE_CASES


def salary_answer():
    return {
        "request_id": "request-1", "answer_status": "SUCCESS", "degraded": False,
        "answer_label": "根拠十分", "answer": "回答分類: 根拠十分\n回答:\n毎月21日です。",
        "references": [{"document_id": "DOC-001", "heading": "3. 給与支給日",
                        "document_name": "給与制度規程", "content": "毎月21日に支給する。"}],
        "generation": {"finish_reason": "STOP"},
    }


def test_standalone_smoke_runs_no_storage_mutation_and_retains_review_requirement():
    with (
        patch.object(manage_rag_v2, "migrate") as migrate,
        patch.object(manage_rag_v2, "ingest") as ingest,
        patch.object(manage_rag_v2, "ingest_reviewed_visual_fixtures") as ingest_visual,
        patch.object(manage_rag_v2, "rebuild_qdrant") as rebuild,
        patch.object(manage_rag_v2, "generate_qdrant_answer", return_value=salary_answer()) as generate,
    ):
        report = manage_rag_v2.smoke(case_ids=["salary_day"], max_cases=1, max_attempts=1)
    for mutation in (migrate, ingest, ingest_visual, rebuild):
        mutation.assert_not_called()
    generate.assert_called_once_with(SMOKE_CASES[0].question)
    assert report["structural_passed"]
    assert report["semantic_review_status"] == "PENDING"
    assert report["release_ready"] is False
    assert report["attempts"] == 1
    assert report["results"][0]["response"]["answer"] == salary_answer()["answer"]


@pytest.mark.parametrize("error,kind", [
    (RuntimeError("503 UNAVAILABLE secret-response"), "PROVIDER_ERROR"),
    (RuntimeError("429 RESOURCE_EXHAUSTED secret-response"), "PROVIDER_ERROR"),
    (RuntimeError("401 invalid API key secret-response"), "PROVIDER_ERROR"),
    (ValueError("schema secret-response"), "FORMAT_ERROR"),
    (RuntimeError("db secret-response"), "EXECUTION_ERROR"),
])
def test_smoke_classifies_errors_without_repeating_sensitive_message(error, kind):
    with patch.object(manage_rag_v2, "generate_qdrant_answer", side_effect=error) as generate:
        report = manage_rag_v2.smoke()
    assert not report["structural_passed"]
    assert report["results"][0]["failure_kind"] == kind
    assert "secret-response" not in json.dumps(report)
    assert report["not_run_case_ids"] == [case.case_id for case in SMOKE_CASES[1:]]
    generate.assert_called_once()


def test_smoke_retries_are_finite_and_request_budget_includes_failed_attempts():
    with patch.object(manage_rag_v2, "generate_qdrant_answer", side_effect=[
        RuntimeError("503 UNAVAILABLE"), RuntimeError("503 UNAVAILABLE"), salary_answer(),
    ]) as generate:
        report = manage_rag_v2.smoke(case_ids=["salary_day"], max_attempts=2,
                                     max_503_retries=2, sleep=lambda _: None)
    assert generate.call_count == 2
    assert report["attempts"] == 2
    assert not report["structural_passed"]


def test_retry_cannot_spend_the_remaining_case_budget_and_claim_completion():
    with patch.object(manage_rag_v2, "generate_qdrant_answer", side_effect=[
        RuntimeError("503 UNAVAILABLE"), salary_answer(),
    ]) as generate:
        report = manage_rag_v2.smoke(case_ids=["salary_day", "missing_document"], max_attempts=2,
                                     max_503_retries=1, sleep=lambda _: None)
    assert generate.call_count == 2
    assert report["attempts"] == 2
    assert report["not_run_case_ids"] == ["missing_document"]
    assert report["results"][-1]["status"] == "NOT_RUN"
    assert report["results"][-1]["failure_kind"] == "REQUEST_BUDGET_EXCEEDED"
    assert not report["structural_passed"]


@pytest.mark.parametrize("kwargs", [
    {"case_ids": []}, {"case_ids": ["unknown"]},
    {"case_ids": ["salary_day", "salary_day"]},
    {"max_cases": 0}, {"max_cases": 4}, {"max_attempts": 0},
    {"max_attempts": 4}, {"max_503_retries": -1}, {"max_503_retries": 3},
])
def test_invalid_or_insufficient_budget_fails_before_external_calls(kwargs):
    with patch.object(manage_rag_v2, "generate_qdrant_answer") as generate:
        with pytest.raises(ValueError):
            manage_rag_v2.smoke(**kwargs)
    generate.assert_not_called()


def test_cli_success_prints_summary_and_writes_separate_exclusive_review_artifact(tmp_path, capsys):
    output = tmp_path / "smoke.json"
    argv = ["manage_rag_v2", "smoke", "--case", "salary_day", "--output", str(output)]
    generated = salary_answer()
    generated["answer"] += " fake-response-marker"
    with (
        patch("sys.argv", argv),
        patch.object(manage_rag_v2, "generate_qdrant_answer", return_value=generated),
    ):
        assert manage_rag_v2.main() == 0
    summary = json.loads(capsys.readouterr().out)
    full = json.loads(output.read_text())
    assert summary["structural_passed"]
    assert "response" not in summary["results"][0]
    assert "fake-response-marker" not in json.dumps(summary, ensure_ascii=False)
    assert full["results"][0]["response"]["answer"] == generated["answer"]
    with (
        patch("sys.argv", argv),
        patch.object(manage_rag_v2, "generate_qdrant_answer") as generate,
    ):
        assert manage_rag_v2.main() != 0
    generate.assert_not_called()
    assert json.loads(output.read_text()) == full


def test_cli_failure_exits_nonzero_and_does_not_leak_provider_details(capsys):
    with (
        patch("sys.argv", ["manage_rag_v2", "smoke", "--case", "salary_day"]),
        patch.object(manage_rag_v2, "generate_qdrant_answer", side_effect=RuntimeError("503 UNAVAILABLE token=SECRET")),
    ):
        assert manage_rag_v2.main() == 1
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    assert json.loads(output.out)["results"][0]["failure_kind"] == "PROVIDER_ERROR"


def test_bootstrap_incomplete_result_raises_failure_despite_nonempty_safe_text():
    result = salary_answer()
    result.update({"answer_status": "GENERATION_INCOMPLETE", "answer_label": None, "degraded": True})
    with (
        patch.object(manage_rag_v2, "migrate"), patch.object(manage_rag_v2, "ingest"),
        patch.object(manage_rag_v2, "ingest_reviewed_visual_fixtures"),
        patch.object(manage_rag_v2, "reconcile", return_value={"consistent": True}),
        patch.object(manage_rag_v2, "generate_qdrant_answer", return_value=result),
    ):
        with pytest.raises(manage_rag_v2.SmokeFailure) as error:
            manage_rag_v2.bootstrap_cloud()
    assert error.value.report["results"][0]["failure_kind"] == "GENERATION_INCOMPLETE"


def test_smoke_does_not_serialize_visual_image_bytes_in_review_artifact():
    result = salary_answer()
    result["references"].append({"document_id": "irrelevant", "content": "another reference",
                                  "visual_asset": {"content": b"image", "mime_type": "image/png", "page_number": 1}})
    with patch.object(manage_rag_v2, "generate_qdrant_answer", return_value=result):
        report = manage_rag_v2.smoke(case_ids=["salary_day"])
    json.dumps(report)
    asset = report["results"][0]["response"]["references"][1]["visual_asset"]
    assert "content" not in asset
    assert asset["image_loaded"] is True


@pytest.mark.parametrize("fail_on_third", [False, True])
def test_full_five_case_suite_requires_every_case_and_stops_on_failure(fail_on_third):
    answers = [salary_answer() for _ in range(5)]
    answers[1].update({"answer_label": "文書不足", "references": [],
                       "answer": "回答分類: 文書不足\n回答:\n取得した文書では計算式を確認できません。所管部署へ確認してください。"})
    answers[2].update({"answer_label": "判断要", "answer": "回答分類: 判断要\n回答:\n契約、家賃、届出を確認してください。",
                       "references": [{"document_id": "DOC-002", "heading": "3.2 支給要件", "content": "本人名義、家賃、住居届"}]})
    answers[3]["references"] = [{"document_id": "visual-demo-table_dev_001", "content": "通勤手当 支給額・区分表",
                                  "visual_asset": {"content": b"fixture-image", "mime_type": "image/png", "page_number": 1}}]
    answers[4].update({"answer_label": "判断要", "answer": "回答分類: 判断要\n回答:\n起算規則を確認する必要があります。",
                       "references": [{"document_id": "DOC-004", "heading": "2.2 提出期限", "content": "14日以内に提出"}]})
    if fail_on_third:
        answers[2]["answer_status"] = "GENERATION_INCOMPLETE"
    with (
        patch("sys.argv", ["manage_rag_v2", "smoke", "--max-cases", "5", "--max-attempts", "5", "--max-503-retries", "0"]),
        patch.object(manage_rag_v2, "generate_qdrant_answer", side_effect=answers) as generate,
    ):
        assert manage_rag_v2.main() == (1 if fail_on_third else 0)
    assert generate.call_count == (3 if fail_on_third else 5)
