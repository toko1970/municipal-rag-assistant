from eval.score_text_holdout import _wilson


def test_wilson_interval_contains_observed_rate() -> None:
    interval = _wilson(80, 100)

    assert interval["low"] < 0.8 < interval["high"]


def test_wilson_interval_handles_empty_input() -> None:
    assert _wilson(0, 0) == {"low": 0.0, "high": 0.0}
