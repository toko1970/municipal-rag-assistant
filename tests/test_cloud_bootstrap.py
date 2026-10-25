import json
from unittest.mock import patch

import cloud_bootstrap
from scripts.manage_rag_v2 import SmokeFailure


def test_cloud_bootstrap_entrypoint_prints_bootstrap_result(capsys) -> None:
    expected = {"migration": "head", "consistency": {"consistent": True}}

    with patch("cloud_bootstrap.bootstrap_cloud", return_value=expected) as bootstrap:
        assert cloud_bootstrap.main() == 0

    bootstrap.assert_called_once_with()
    assert json.loads(capsys.readouterr().out) == expected


def test_cloud_bootstrap_entrypoint_returns_nonzero_on_failed_smoke(capsys) -> None:
    report = {"structural_passed": False, "results": [{
        "case_id": "salary_day", "status": "FAIL", "failure_kind": "GENERATION_INCOMPLETE",
        "response": {"answer": "do not log this body"},
    }]}
    with patch("cloud_bootstrap.bootstrap_cloud", side_effect=SmokeFailure(report)):
        assert cloud_bootstrap.main() == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["structural_passed"] is False
    assert "response" not in summary["results"][0]
