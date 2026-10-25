"""Release acceptance is bound to the tested revision and fails closed."""

from copy import deepcopy
import json
import subprocess
import sys

import pytest

from scripts.release_gate import (
    CASE_IDS,
    ReleaseGateError,
    build_manifest,
    validate_promotion,
    check_runtime_match,
    rollback_argument,
)


IMAGE = (
    "asia-northeast1-docker.pkg.dev/municipal-rag-portfolio/municipal-rag-images/municipal-rag-assistant@sha256:"
    + "a" * 64
)
COMMIT = "b" * 40
REVISION = "municipal-rag-assistant-r123-1"
OLD = "municipal-rag-assistant-old"
TAG = "review-123-1"
URL = "https://review-123-1---municipal-rag-assistant-example.a.run.app"


def fixture():
    container = {
        "image": IMAGE,
        "env": [
            {"name": "ANSWER_GENERATION_FLOW", "value": "autoresearch_candidate"},
            {
                "name": "DATABASE_URL",
                "valueFrom": {"secretKeyRef": {"name": "db", "key": "1"}},
            },
        ],
    }
    spec = {
        "serviceAccountName": "runtime@example.iam.gserviceaccount.com",
        "containers": [container],
    }
    annotations = {"run.googleapis.com/cloudsql-instances": "project:region:db"}
    revision = {
        "metadata": {
            "name": REVISION,
            "labels": {"commit-sha": COMMIT},
            "annotations": deepcopy(annotations),
        },
        "spec": deepcopy(spec),
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    before = {"status": {"traffic": [{"revisionName": OLD, "percent": 100}]}}
    after = {
        "status": {
            "traffic": [
                {"revisionName": OLD, "percent": 100},
                {"revisionName": REVISION, "tag": TAG, "url": URL},
            ]
        }
    }
    task = deepcopy(spec)
    task["containers"][0].update(
        {
            "command": ["python"],
            "args": [
                "-m",
                "scripts.manage_rag_v2",
                "smoke",
                "--max-cases",
                "5",
                "--max-attempts",
                "5",
                "--max-503-retries",
                "0",
            ],
        }
    )
    task["maxRetries"] = 0
    execution = {
        "metadata": {
            "name": "municipal-rag-bootstrap-123",
            "annotations": deepcopy(annotations),
        },
        "spec": {
            "taskCount": 1,
            "template": {
                "metadata": {"annotations": deepcopy(annotations)},
                "spec": task,
            },
        },
        "status": {
            "conditions": [{"type": "Completed", "status": "True"}],
            "succeededCount": 1,
            "failedCount": 0,
        },
    }
    return before, after, revision, execution


def prepared():
    return build_manifest(
        *fixture(),
        commit=COMMIT,
        run_id="123",
        run_attempt="1",
        repository="toko1970/municipal-rag-assistant",
        tag=TAG,
        expected_revision=REVISION,
        expected_image=IMAGE,
    )


def review(manifest):
    return {
        "schema_version": "rag-release-review-v1",
        "candidate_run_id": "123",
        "candidate_run_attempt": "1",
        "revision": REVISION,
        "commit": COMMIT,
        "image": IMAGE,
        "manifest_sha256": manifest["manifest_sha256"],
        "reviewed_by": "owner",
        "reviewed_at": "2026-10-25T16:00:00+09:00",
        "tagged_url": URL,
        "cases": [
            {
                "case_id": key,
                "semantic": "PASS",
                "ui": "PASS",
                "notes": "根拠と表示を確認",
            }
            for key in CASE_IDS
        ],
    }


def source_run():
    return {
        "id": 123,
        "run_attempt": 1,
        "head_sha": COMMIT,
        "head_branch": "main",
        "event": "push",
        "conclusion": "success",
        "status": "completed",
        "path": ".github/workflows/ci.yml",
        "repository": {"full_name": "toko1970/municipal-rag-assistant"},
    }


def test_preparation_does_not_claim_semantic_acceptance_and_keeps_rollback():
    manifest = prepared()
    assert manifest["semantic_review_status"] == "PENDING"
    assert manifest["release_ready"] is False
    assert manifest["revision"] == REVISION
    assert manifest["previous_traffic"] == {OLD: 100}
    assert "DATABASE_URL" not in json.dumps(manifest)
    assert rollback_argument(manifest) == f"{OLD}=100"


@pytest.mark.parametrize("change", ["image", "env", "account", "cloudsql"])
def test_runtime_mismatch_fails_before_acceptance(change):
    _, _, revision, execution = fixture()
    if change == "image":
        execution["spec"]["template"]["spec"]["containers"][0]["image"] = IMAGE.replace(
            "a" * 64, "c" * 64
        )
    elif change == "env":
        execution["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] = (
            "production"
        )
    elif change == "account":
        execution["spec"]["template"]["spec"]["serviceAccountName"] = "wrong"
    else:
        execution["spec"]["template"]["metadata"]["annotations"][
            "run.googleapis.com/cloudsql-instances"
        ] = "wrong"
    with pytest.raises(ReleaseGateError, match="runtime"):
        check_runtime_match(revision, execution)


@pytest.mark.parametrize(
    "failure",
    [
        "failed_job",
        "partial_job",
        "bootstrap",
        "wrong_tag",
        "traffic_changed",
        "wrong_commit",
        "wrong_revision",
    ],
)
def test_preparation_rejects_incomplete_or_mismatched_evidence(failure):
    before, after, revision, execution = fixture()
    if failure == "failed_job":
        execution["status"]["conditions"][0]["status"] = "False"
    elif failure == "partial_job":
        execution["status"]["succeededCount"] = 0
    elif failure == "bootstrap":
        execution["spec"]["template"]["spec"]["containers"][0]["args"] = [
            "cloud_bootstrap.py"
        ]
    elif failure == "wrong_tag":
        after["status"]["traffic"][1]["revisionName"] = OLD
    elif failure == "traffic_changed":
        after["status"]["traffic"][0]["revisionName"] = REVISION
    elif failure == "wrong_commit":
        revision["metadata"]["labels"]["commit-sha"] = "0" * 40
    else:
        revision["metadata"]["name"] = OLD
    with pytest.raises(ReleaseGateError):
        build_manifest(
            before,
            after,
            revision,
            execution,
            commit=COMMIT,
            run_id="123",
            run_attempt="1",
            repository="toko1970/municipal-rag-assistant",
            tag=TAG,
            expected_revision=REVISION,
            expected_image=IMAGE,
        )


def test_full_manual_review_can_select_only_tested_revision():
    manifest = prepared()
    result = validate_promotion(
        manifest, review(manifest), source_run(), fixture()[1], fixture()[2]
    )
    assert result["revision"] == REVISION
    assert result["traffic_argument"] == f"{REVISION}=100"
    assert result["rollback_argument"] == f"{OLD}=100"


@pytest.mark.parametrize(
    "failure",
    [
        "pending",
        "missing_case",
        "duplicate_case",
        "missing_ui",
        "wrong_run",
        "wrong_image",
        "empty_notes",
        "different_url",
        "tampered_manifest",
        "newer_traffic",
        "unsuccessful_run",
    ],
)
def test_promotion_fails_closed_without_bound_complete_manual_acceptance(failure):
    manifest = prepared()
    result = review(manifest)
    run = source_run()
    current = fixture()[1]
    if failure == "pending":
        result["cases"][0]["semantic"] = "PENDING"
    elif failure == "missing_case":
        result["cases"].pop()
    elif failure == "duplicate_case":
        result["cases"][1] = result["cases"][0]
    elif failure == "missing_ui":
        del result["cases"][0]["ui"]
    elif failure == "wrong_run":
        result["candidate_run_id"] = "122"
    elif failure == "wrong_image":
        result["image"] = "latest"
    elif failure == "empty_notes":
        result["cases"][0]["notes"] = ""
    elif failure == "different_url":
        result["tagged_url"] = "https://service-default.example.com"
    elif failure == "tampered_manifest":
        manifest["previous_traffic"] = {"unexpected": 100}
    elif failure == "newer_traffic":
        current["status"]["traffic"][0]["revisionName"] = "a-newer-release"
    else:
        run["conclusion"] = "failure"
    with pytest.raises(ReleaseGateError):
        validate_promotion(manifest, result, run, current, fixture()[2])


def test_cli_invalid_promotion_is_nonzero_and_never_runs_gcloud(tmp_path):
    manifest = prepared()
    for name, value in {
        "manifest": manifest,
        "review": review(manifest),
        "run": source_run(),
        "service": fixture()[1],
        "revision": fixture()[2],
    }.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    (tmp_path / "review.json").write_text("{}")
    command = [
        sys.executable,
        "-m",
        "scripts.release_gate",
        "approve",
        "--manifest",
        str(tmp_path / "manifest.json"),
        "--review",
        str(tmp_path / "review.json"),
        "--source-run",
        str(tmp_path / "run.json"),
        "--service",
        str(tmp_path / "service.json"),
        "--revision",
        str(tmp_path / "revision.json"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "traffic_argument" not in result.stdout


def test_workflow_preserves_required_gates_and_cannot_auto_promote():
    from pathlib import Path
    import yaml

    ci = yaml.load(Path(".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    promotion = yaml.load(
        Path(".github/workflows/promote.yml").read_text(), Loader=yaml.BaseLoader
    )
    prepare = ci["jobs"]["deploy"]
    promote = promotion["jobs"]["promote"]
    assert set(prepare["needs"]) == {"test-and-lint", "integration", "terraform-check"}
    assert prepare["environment"] == promote["environment"] == "production"
    assert (
        prepare["concurrency"]
        == promote["concurrency"]
        == {"group": "production-deploy", "cancel-in-progress": "false"}
    )
    assert (
        "vars.ENABLE_CD == 'true'" in prepare["if"]
        and "vars.ENABLE_CD == 'true'" in promote["if"]
    )
    assert "github.ref == 'refs/heads/main'" in promote["if"]
    deployments = [
        step["with"]
        for step in prepare["steps"]
        if step.get("uses", "").startswith("google-github-actions/deploy-cloudrun@")
    ]
    service = next(step for step in deployments if "service" in step)
    job = next(step for step in deployments if "job" in step)
    assert service["no_traffic"] == "true"
    assert service["image"] == job["image"]
    assert (
        service["env_vars"] == job["env_vars"] and service["secrets"] == job["secrets"]
    )
    assert "--max-retries=0" in job["flags"] and "--tasks=1" in job["flags"]
    automatic_scripts = "\n".join(step.get("run", "") for step in prepare["steps"])
    assert "update-traffic" not in automatic_scripts
    assert "cloud_bootstrap.py" not in Path(".github/workflows/ci.yml").read_text()
    promotion_scripts = [step.get("run", "") for step in promote["steps"]]
    approve_index = next(
        i
        for i, value in enumerate(promotion_scripts)
        if "release_gate approve" in value
    )
    change_index = next(
        i for i, value in enumerate(promotion_scripts) if "update-traffic" in value
    )
    assert approve_index < change_index
    assert "--to-latest" not in "\n".join(promotion_scripts)
    assert '--to-revisions="$target"' in promotion_scripts[change_index]
    assert "trap finish EXIT" in promotion_scripts[change_index]
    assert "trap 'exit 130' INT" in promotion_scripts[change_index]
    assert "trap 'exit 143' TERM" in promotion_scripts[change_index]
    assert not any(step.get("continue-on-error") == "true" for step in promote["steps"])


def test_workflow_shell_fragments_parse_before_cloud_execution(tmp_path):
    from pathlib import Path
    import yaml

    for workflow in (".github/workflows/ci.yml", ".github/workflows/promote.yml"):
        data = yaml.load(Path(workflow).read_text(), Loader=yaml.BaseLoader)
        for name, job in data["jobs"].items():
            for index, step in enumerate(job["steps"]):
                if "run" not in step:
                    continue
                script = tmp_path / f"{Path(workflow).stem}-{name}-{index}.sh"
                script.write_text(step["run"])
                result = subprocess.run(
                    ["bash", "-n", str(script)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert result.returncode == 0, result.stderr


def test_smoke_job_arguments_survive_action_flag_normalization(capsys):
    """Exercise the leading-dash failure seen in Cloud Run preparation.

    deploy-cloudrun normalizes --key=value to separate argv entries. Python's
    argument parser then rejects a value beginning with -m as another option.
    The documented gcloud list delimiter prefix preserves the same task argv
    while making the outer --args value unambiguous.
    """
    import argparse
    from pathlib import Path
    import shlex
    import yaml

    from scripts.release_gate import SMOKE_ARGS

    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--args")
    with pytest.raises(SystemExit) as rejected:
        parser.parse_args(["--args", ",".join(SMOKE_ARGS)])
    assert rejected.value.code == 2
    assert "expected one argument" in capsys.readouterr().err

    ci = yaml.load(Path(".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    job = next(
        step["with"] for step in ci["jobs"]["deploy"]["steps"]
        if "job" in step.get("with", {})
    )
    # Reproduce the action boundary observed in the failed cloud command.
    action_argv = [
        part for flag in shlex.split(job["flags"]) for part in flag.split("=", 1)
    ]
    parsed, _ = parser.parse_known_args(action_argv)
    assert parsed.args.startswith("^,^")
    assert parsed.args.removeprefix("^,^").split(",") == SMOKE_ARGS


def test_outcome_receipt_distinguishes_successful_promotion_from_rollback():
    from scripts.release_gate import record_traffic_outcome

    manifest = prepared()
    promoted = {"status": {"traffic": [{"revisionName": REVISION, "percent": 100}]}}
    receipt = record_traffic_outcome(manifest, promoted, "PROMOTED")
    assert receipt["observed_traffic"] == {REVISION: 100}
    with pytest.raises(ReleaseGateError, match="traffic"):
        record_traffic_outcome(manifest, fixture()[1], "PROMOTED")
    assert (
        record_traffic_outcome(manifest, fixture()[1], "ROLLED_BACK")["outcome"]
        == "ROLLED_BACK"
    )


@pytest.mark.parametrize(
    "failure, expected_code, expected_outcome",
    [
        ("success", 0, "PROMOTED"),
        ("health_failure", 1, "ROLLED_BACK"),
        ("partial_update_failure", 1, "ROLLED_BACK"),
        ("int_during_update", 130, "ROLLED_BACK"),
        ("term_during_update", 143, "ROLLED_BACK"),
        ("int_after_update", 130, "ROLLED_BACK"),
        ("term_after_update", 143, "ROLLED_BACK"),
        ("explicit_exit_after_update", 9, "ROLLED_BACK"),
        ("cancel_before_update", 143, None),
        ("cancel_after_verified", 143, "PROMOTED"),
        ("rollback_failure", 1, "ROLLBACK_UNCONFIRMED"),
    ],
)
def test_actual_promotion_shell_restores_traffic_on_failure_and_cancellation(
    tmp_path, failure, expected_code, expected_outcome
):
    """Run the real workflow shell; fake only external gcloud/curl boundaries."""
    import os
    from pathlib import Path
    import yaml

    root = Path(__file__).resolve().parents[1]
    data = yaml.load(
        (root / ".github/workflows/promote.yml").read_text(), Loader=yaml.BaseLoader
    )
    script = next(
        step["run"]
        for step in data["jobs"]["promote"]["steps"]
        if step.get("name", "").startswith("Promote only the verified revision")
    )
    mutation = 'gcloud run services update-traffic municipal-rag-assistant --project=municipal-rag-portfolio --region=asia-northeast1 --to-revisions="$target"'
    if failure == "explicit_exit_after_update":
        script = script.replace(mutation, mutation + "\nexit 9")
    elif failure == "cancel_before_update":
        script = script.replace(
            "traffic_change_started=1", 'kill -TERM "$$"\ntraffic_change_started=1'
        )
    elif failure == "cancel_after_verified":
        script = script.replace(
            "promotion_verified=1", 'promotion_verified=1\nkill -TERM "$$"'
        )
    evidence = tmp_path / "release-evidence"
    evidence.mkdir()
    runner = tmp_path / "runner"
    runner.mkdir()
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "python").symlink_to(sys.executable)
    manifest = prepared()
    (evidence / "candidate.json").write_text(json.dumps(manifest))
    approval = validate_promotion(
        manifest, review(manifest), source_run(), fixture()[1], fixture()[2]
    )
    (evidence / "promotion.json").write_text(json.dumps(approval))
    (runner / "review.json").write_text(json.dumps(review(manifest)))
    state = tmp_path / "traffic.json"
    state.write_text(json.dumps({OLD: 100}))
    calls = tmp_path / "calls.jsonl"
    gcloud = binary / "gcloud"
    gcloud.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, signal, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["TEST_TRAFFIC"])
mode = os.environ["TEST_FAILURE"]
with Path(os.environ["TEST_CALLS"]).open("a") as handle:
    handle.write(json.dumps(args) + "\n")
if "update-traffic" in args:
    target = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--to-revisions="))
    desired = dict((item.rsplit("=", 1)[0], int(item.rsplit("=", 1)[1])) for item in target.split(","))
    promoting = list(desired)[0] == os.environ["TEST_REVISION"]
    if not promoting and mode == "rollback_failure":
        sys.exit(1)
    state.write_text(json.dumps(desired))
    if promoting and mode == "partial_update_failure":
        sys.exit(1)  # server changed traffic; client reported failure
    if promoting and mode in ("int_during_update", "term_during_update"):
        os.kill(os.getppid(), signal.SIGINT if mode.startswith("int_") else signal.SIGTERM)
elif "describe" in args:
    observed = json.loads(state.read_text())
    promoting = list(observed)[0] == os.environ["TEST_REVISION"]
    if promoting and mode in ("int_after_update", "term_after_update"):
        os.kill(os.getppid(), signal.SIGINT if mode.startswith("int_") else signal.SIGTERM)
    print(json.dumps({"status":{"traffic":[{"revisionName": key, "percent": value} for key, value in observed.items()], "url":"https://example.run.app"}}))
else:
    sys.exit(2)
"""
    )
    gcloud.chmod(0o755)
    curl = binary / "curl"
    curl.write_text(
        '#!/bin/bash\nif [[ "$TEST_FAILURE" == "health_failure" || "$TEST_FAILURE" == "rollback_failure" ]]; then exit 1; fi\nexit 0\n'
    )
    curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": str(root),
        "RUNNER_TEMP": str(runner),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "TEST_TRAFFIC": str(state),
        "TEST_CALLS": str(calls),
        "TEST_FAILURE": failure,
        "TEST_REVISION": REVISION,
    }
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode == expected_code, completed.stderr
    if expected_outcome is None:
        assert not calls.exists()
        assert not (evidence / "outcome.json").exists()
        assert json.loads(state.read_text()) == {OLD: 100}
        return
    receipt = json.loads((evidence / "outcome.json").read_text())
    assert receipt["outcome"] == expected_outcome
    updates = [
        row
        for row in map(json.loads, calls.read_text().splitlines())
        if "update-traffic" in row
    ]
    if expected_outcome == "ROLLED_BACK":
        assert len(updates) == 2
        assert json.loads(state.read_text()) == {OLD: 100}
        assert receipt["observed_traffic"] == {OLD: 100}
    elif expected_outcome == "PROMOTED":
        assert len(updates) == 1
        assert json.loads(state.read_text()) == {REVISION: 100}
    else:
        assert receipt["manual_recovery_required"] is True
        assert json.loads(state.read_text()) == {REVISION: 100}
