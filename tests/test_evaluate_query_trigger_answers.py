from eval.evaluate_query_trigger_answers import _pacing_delay


def test_pacing_delay_preserves_minimum_start_interval() -> None:
    assert _pacing_delay(None, now=100.0, interval=15.0) == 0.0
    assert _pacing_delay(100.0, now=104.0, interval=15.0) == 11.0
    assert _pacing_delay(100.0, now=116.0, interval=15.0) == 0.0
