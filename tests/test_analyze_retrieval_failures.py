from eval.analyze_retrieval_failures import analyze_records, classify_record


def _record(**overrides):
    record = {
        "question_id": "Q1",
        "question": "質問",
        "retrieval_applicable": "1",
        "expected_document_ids": "DOC-001",
        "expected_evidence": "DOC-001::見出し",
        "expected_answer_type": "根拠十分",
        "difficulty": "direct",
        "retrieved_document_ids": "DOC-001",
        "retrieved_headings": "別見出し",
        "hit_at_5": "1",
        "evidence_hit_at_5": "0",
    }
    record.update(overrides)
    return record


def test_classifies_document_and_section_failures_separately() -> None:
    assert classify_record(_record(hit_at_5="0"), 5) == "document_missing"
    assert classify_record(_record(), 5) == "section_missing"
    assert classify_record(_record(evidence_hit_at_5="1"), 5) == "success"


def test_excludes_unanswerable_rows_and_summarizes_failure_dimensions() -> None:
    records = [
        _record(),
        _record(
            question_id="Q2",
            expected_document_ids="DOC-001|DOC-002",
            expected_evidence="DOC-001::節1|DOC-002::節2",
            difficulty="multi_document",
            hit_at_5="0",
        ),
        _record(
            question_id="Q3",
            retrieval_applicable="0",
            expected_document_ids="",
            expected_evidence="",
            hit_at_5="",
            evidence_hit_at_5="",
        ),
    ]

    summary, failures = analyze_records(records, 5)

    assert summary["evidence_scored"] == 2
    assert summary["retrieval_not_applicable"] == 1
    assert summary["failure_categories"] == {
        "document_missing": 1,
        "section_missing": 1,
    }
    assert summary["failure_by_required_document_count"] == {"1": 1, "2": 1}
    assert [row["failure_category"] for row in failures] == [
        "section_missing",
        "document_missing",
    ]


def test_rejects_unsupported_cutoff() -> None:
    try:
        analyze_records([_record()], 2)
    except ValueError as error:
        assert "1、3、5" in str(error)
    else:
        raise AssertionError("unsupported cutoff was accepted")
