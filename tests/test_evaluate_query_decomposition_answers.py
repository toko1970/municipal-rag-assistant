from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_query_decomposition_answers import (
    _provider_error,
    _scenario_logical_calls,
)


def test_recognizes_actual_gemini_503_as_provider_error() -> None:
    error = "ServerError: 503 UNAVAILABLE. model is currently experiencing high demand"
    assert _provider_error(error)


def test_counts_only_calls_that_were_attempted() -> None:
    failed_generation = EvaluationLogger(generation={"status": "GENERATION_FAILED"})
    assert _scenario_logical_calls(failed_generation, None) == 1

    completed_without_resolver = EvaluationLogger(generation={"status": "SUCCESS"})
    assert (
        _scenario_logical_calls(
            completed_without_resolver,
            {"version_resolution": {"status": "NOT_REQUIRED"}},
        )
        == 2
    )

    completed_with_resolver = EvaluationLogger(generation={"status": "SUCCESS"})
    assert (
        _scenario_logical_calls(
            completed_with_resolver,
            {"version_resolution": {"status": "SUCCESS"}},
        )
        == 3
    )
