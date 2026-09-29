import json
from pathlib import Path

import pytest

from src.temporal_evidence import should_use_deadline_calculation


CASES_PATH = Path(__file__).parents[1] / "eval" / "deadline_route_cases.json"
PAYLOAD = json.loads(CASES_PATH.read_text(encoding="utf-8"))
CASES = PAYLOAD["development"] + PAYLOAD["acceptance"]


def test_deadline_route_case_ids_are_unique() -> None:
    ids = [case["id"] for case in CASES]

    assert len(ids) == len(set(ids))
    assert len(PAYLOAD["development"]) == 20
    assert len(PAYLOAD["acceptance"]) == 12


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_deadline_route_contract(case: dict[str, object]) -> None:
    assert should_use_deadline_calculation(str(case["question"])) is bool(
        case["expected_route"]
    )
