import json
from pathlib import Path

import pytest

from eval.run_visual_extraction_baseline import run_baseline


ROOT = Path(__file__).resolve().parents[1]


class NoCallProvider:
    def generate_structured_multimodal(self, *_args, **_kwargs):
        raise AssertionError("reused candidateではAPIを呼びません")


class ConnectError(Exception):
    pass


class BlockedProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate_structured_multimodal(self, *_args, **_kwargs):
        self.calls += 1
        raise ConnectError("network unavailable")


def test_baseline_reuses_candidate_and_writes_metrics(tmp_path: Path) -> None:
    fixture_id = "flowchart_dev_001"
    source_manifest = json.loads(
        (
            ROOT / "eval/visual_fixtures/manifests/development_manifest.json"
        ).read_text()
    )
    source_manifest["fixtures"] = source_manifest["fixtures"][:1]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(source_manifest), encoding="utf-8")
    reuse_dir = tmp_path / "reuse"
    reuse_dir.mkdir()
    gold = json.loads(
        (ROOT / "eval/visual_fixtures/gold/flowchart_dev_001.json").read_text()
    )
    (reuse_dir / f"{fixture_id}.json").write_text(json.dumps(gold))
    (reuse_dir / f"{fixture_id}.metadata.json").write_text(
        json.dumps(
            {
                "provider": "gemini",
                "model": "visual-test",
                "input_tokens": 10,
                "output_tokens": 20,
            }
        )
    )

    summary = run_baseline(
        manifest_path=manifest,
        output_dir=tmp_path / "result",
        provider=NoCallProvider(),
        reuse_dir=reuse_dir,
        max_api_calls=0,
    )

    assert summary["api_calls"] == 0
    assert summary["validated_count"] == 1
    assert summary["gate_passed_count"] == 1
    assert summary["total_input_tokens"] == 10
    assert (tmp_path / "result" / "summary.json").is_file()


def test_baseline_stops_before_calls_when_api_cap_is_too_small(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="上限を超えます"):
        run_baseline(
            manifest_path=(
                ROOT / "eval/visual_fixtures/manifests/development_manifest.json"
            ),
            output_dir=tmp_path / "result",
            provider=NoCallProvider(),
            reuse_dir=None,
            max_api_calls=5,
        )

    assert not (tmp_path / "result").exists()


def test_baseline_stops_repeating_after_shared_transport_failure(
    tmp_path: Path,
) -> None:
    provider = BlockedProvider()

    summary = run_baseline(
        manifest_path=(
            ROOT / "eval/visual_fixtures/manifests/development_manifest.json"
        ),
        output_dir=tmp_path / "result",
        provider=provider,
        reuse_dir=None,
        max_api_calls=6,
    )

    assert provider.calls == 1
    assert summary["api_calls"] == 1
    assert summary["error_count"] == 1
    assert summary["skipped_count"] == 5
