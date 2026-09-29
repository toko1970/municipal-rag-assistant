from eval.evaluate_deadline_calculation_v1_1 import SCENARIO_IDS


def test_deadline_pilot_contains_six_dates_and_two_controls() -> None:
    assert len([item for item in SCENARIO_IDS if "-D" in item]) == 6
    assert len([item for item in SCENARIO_IDS if "-C" in item]) == 2
