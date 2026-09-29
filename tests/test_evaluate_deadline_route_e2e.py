from eval.evaluate_deadline_route_e2e import ROUTE_VARIANTS
from src.temporal_evidence import should_use_deadline_calculation


def test_route_e2e_variants_are_small_and_all_select_deadline_route() -> None:
    assert len(ROUTE_VARIANTS) == 4
    assert len({row["id"] for row in ROUTE_VARIANTS}) == 4
    assert all(should_use_deadline_calculation(row["question"]) for row in ROUTE_VARIANTS)
