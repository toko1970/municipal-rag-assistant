from eval.compare_contextual_top_k import metrics_for_ranking, smallest_complete_k


def test_metrics_find_smallest_k_with_all_required_evidence() -> None:
    retrieved = [
        ("DOC-1", "A"),
        ("DOC-2", "noise"),
        ("DOC-2", "B"),
    ]
    metrics = metrics_for_ranking(
        retrieved,
        required_ids=["DOC-1", "DOC-2"],
        required_evidence=[("DOC-1", "A"), ("DOC-2", "B")],
        k_values=[1, 2, 3],
    )

    assert metrics["2"]["document_hit"] == 1
    assert metrics["2"]["evidence_hit"] == 0
    assert metrics["3"]["evidence_hit"] == 1
    assert smallest_complete_k(metrics, "document_hit") == 2
    assert smallest_complete_k(metrics, "evidence_hit") == 3


def test_unanswerable_question_is_not_counted_as_retrieval_hit() -> None:
    metrics = metrics_for_ranking(
        [("DOC-1", "A")],
        required_ids=[],
        required_evidence=[],
        k_values=[1],
    )

    assert metrics["1"]["document_hit"] == 0
    assert metrics["1"]["evidence_hit"] == 0
    assert smallest_complete_k(metrics, "evidence_hit") is None
