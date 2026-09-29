import json

from eval.score_text_holdout import _wilson, finalize_score


def test_wilson_interval_contains_observed_rate() -> None:
    interval = _wilson(80, 100)

    assert interval["low"] < 0.8 < interval["high"]


def test_wilson_interval_handles_empty_input() -> None:
    assert _wilson(0, 0) == {"low": 0.0, "high": 0.0}


def test_finalize_marks_content_review_completed(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    review_path = tmp_path / "content_review.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "state": "OPENED",
                "holdout_id": "holdout",
                "questions": {"expression_count": 1},
            }
        ),
        encoding="utf-8",
    )
    review_path.write_text(
        json.dumps(
            {
                "scenario_id": "TH001",
                "variant_type": "formal",
                "execution_ok": True,
                "classification_ok": True,
                "document_retrieval_ok": True,
                "evidence_retrieval_ok": True,
                "content_ok": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "opening_summary.json").write_text(
        json.dumps({"content_review_status": "PENDING"}), encoding="utf-8"
    )

    finalize_score(
        manifest_path=manifest_path,
        review_path=review_path,
        output_dir=tmp_path,
    )

    opening = json.loads((tmp_path / "opening_summary.json").read_text())
    assert opening["content_review_status"] == "COMPLETED"
