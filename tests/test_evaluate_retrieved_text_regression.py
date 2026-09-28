from uuid import uuid4

from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_retrieved_text_regression import (
    _is_provider_error,
    _retrieval_outcome,
)
from src.contracts import IndexableElement, SearchHit


def hit(document_id: str, heading: str) -> SearchHit:
    element = IndexableElement(
        id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        document_name="文書",
        heading=heading,
        content="本文",
        metadata={"document_id": document_id, "heading_path": heading},
    )
    return SearchHit(element=element, score=0.9, rank=1)


def test_retrieval_outcome_requires_every_expected_evidence() -> None:
    logger = EvaluationLogger()
    logger.retrieval_hits = [hit("DOC-001", "規程 > 対象")]
    row = {"expected_evidence": "DOC-001::規程 > 対象|DOC-002::通知 > 期限"}

    result = _retrieval_outcome(row, logger)

    assert result["retrieval_applicable"] is True
    assert result["retrieval_ok"] is False


def test_retrieval_outcome_does_not_treat_unanswerable_as_failure() -> None:
    result = _retrieval_outcome({"expected_evidence": ""}, EvaluationLogger())

    assert result["retrieval_applicable"] is False
    assert result["retrieval_ok"] is None


def test_only_provider_errors_trigger_fail_fast() -> None:
    assert _is_provider_error("Resource_Exhausted: 429 quota")
    assert not _is_provider_error("ValueError: 根拠十分の表示条件を満たしていません")
