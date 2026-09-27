import json
from unittest.mock import patch

import cloud_bootstrap


def test_cloud_bootstrap_entrypoint_prints_bootstrap_result(capsys) -> None:
    expected = {"migration": "head", "consistency": {"consistent": True}}

    with patch("cloud_bootstrap.bootstrap_cloud", return_value=expected) as bootstrap:
        assert cloud_bootstrap.main() == 0

    bootstrap.assert_called_once_with()
    assert json.loads(capsys.readouterr().out) == expected
