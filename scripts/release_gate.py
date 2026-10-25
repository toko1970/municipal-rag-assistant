"""Offline, fail-closed validation of Cloud Run release evidence.

Reads gcloud/GitHub JSON snapshots; never calls a provider, gcloud, or a network.
Only the guarded GitHub workflow is allowed to act on its validated traffic plan.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


CASE_IDS = (
    "salary_day",
    "missing_document",
    "missing_case_facts",
    "visual_table",
    "missing_counting_rule",
)
SMOKE_ARGS = [
    "-m",
    "scripts.manage_rag_v2",
    "smoke",
    "--max-cases=5",
    "--max-attempts=5",
    "--max-503-retries=0",
]
SERVICE = "municipal-rag-assistant"
PROJECT = "municipal-rag-portfolio"
REGION = "asia-northeast1"
CONNECTION_ANNOTATIONS = (
    "run.googleapis.com/cloudsql-instances",
    "run.googleapis.com/vpc-access-connector",
    "run.googleapis.com/vpc-access-egress",
    "run.googleapis.com/network-interfaces",
)


class ReleaseGateError(ValueError):
    """Evidence is missing, inconsistent, stale, or not accepted."""


def _require(condition, message):
    if not condition:
        raise ReleaseGateError(message)


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _named(value, field):
    _require(
        isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,62}", value),
        f"invalid {field}",
    )
    return value


def _image(value):
    _require(
        isinstance(value, str)
        and re.fullmatch(r"[a-z0-9./_-]+@sha256:[a-f0-9]{64}", value),
        "image must be pinned by sha256 digest",
    )
    return value


def traffic(service):
    result = {}
    for item in service.get("status", {}).get("traffic", []):
        percent = item.get("percent", 0)
        _require(
            type(percent) is int and 0 <= percent <= 100, "invalid traffic percentage"
        )
        if percent:
            revision = _named(item.get("revisionName"), "traffic revision")
            result[revision] = result.get(revision, 0) + percent
    _require(
        sum(result.values()) == 100,
        "traffic snapshot must total 100 percent with explicit revisions",
    )
    return result


def _container(spec):
    containers = spec.get("containers", [])
    _require(len(containers) == 1, "runtime requires exactly one container")
    return containers[0]


def _execution(resource):
    # gcloud v1 Job contains an Execution template; Execution is already frozen.
    if "template" in resource.get("spec", {}).get("template", {}).get("spec", {}):
        return resource["spec"]["template"]
    return resource


def _runtime(resource, *, job=False):
    if job:
        execution = _execution(resource)
        task = execution["spec"]["template"]
        spec = task["spec"]
        metadata = execution.get("metadata", {})
        task_annotations = task.get("metadata", {}).get("annotations", {})
    else:
        spec = resource["spec"]
        metadata = resource.get("metadata", {})
        task_annotations = {}
    container = _container(spec)
    annotations = metadata.get("annotations", {})
    connections = {}
    for key in CONNECTION_ANNOTATIONS:
        value = annotations.get(key)
        task_value = task_annotations.get(key)
        _require(
            not (value and task_value and value != task_value),
            "conflicting runtime connection annotations",
        )
        if value or task_value:
            connections[key] = value or task_value
    environment = container.get("env", [])
    _require(
        len({item["name"] for item in environment}) == len(environment),
        "duplicate runtime environment key",
    )
    return {
        "image": _image(container.get("image")),
        "environment": sorted(environment, key=lambda item: item["name"]),
        "service_account": spec.get("serviceAccountName"),
        "connections": connections,
        "volumes": spec.get("volumes", []),
        "volume_mounts": container.get("volumeMounts", []),
        "working_directory": container.get("workingDir", ""),
    }


def check_runtime_match(revision, job_or_execution):
    reference = _runtime(revision)
    candidate = _runtime(job_or_execution, job=True)
    _require(reference == candidate, "job/revision runtime configuration mismatch")
    execution = _execution(job_or_execution)
    task_spec = execution["spec"]["template"]["spec"]
    container = _container(task_spec)
    _require(
        container.get("command") == ["python"] and container.get("args") == SMOKE_ARGS,
        "job must run the fixed smoke-only command",
    )
    _require(execution["spec"].get("taskCount") == 1, "smoke requires exactly one task")
    _require(task_spec.get("maxRetries") == 0, "smoke task retries must be zero")
    return _hash(reference)


def _tagged_url(service, *, tag, revision):
    matches = [
        item
        for item in service.get("status", {}).get("traffic", [])
        if item.get("tag") == tag
    ]
    _require(
        len(matches) == 1 and matches[0].get("revisionName") == revision,
        "tag does not identify the tested revision",
    )
    url = matches[0].get("url", "")
    parsed = urlparse(url)
    _require(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.hostname.endswith(".run.app")
        and parsed.hostname.startswith(tag + "---")
        and not parsed.username
        and not parsed.password
        and not parsed.port
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment,
        "invalid tagged revision URL",
    )
    return url.rstrip("/")


def _revision_check(revision, *, expected_revision, commit, image):
    _require(
        revision.get("metadata", {}).get("name") == expected_revision,
        "revision identity mismatch",
    )
    _require(
        revision["metadata"].get("labels", {}).get("commit-sha") == commit,
        "revision commit mismatch",
    )
    _require(_runtime(revision)["image"] == image, "revision image mismatch")
    _require(
        any(
            item.get("type") == "Ready" and item.get("status") == "True"
            for item in revision.get("status", {}).get("conditions", [])
        ),
        "revision is not ready",
    )


def build_manifest(
    before,
    after,
    revision,
    execution,
    *,
    commit,
    run_id,
    run_attempt,
    repository,
    tag,
    expected_revision,
    expected_image,
):
    _require(re.fullmatch(r"[a-f0-9]{40}", commit), "invalid commit")
    _require(str(run_id).isdigit() and str(run_attempt).isdigit(), "invalid source run")
    _named(expected_revision, "revision")
    _named(tag, "tag")
    _image(expected_image)
    _revision_check(
        revision,
        expected_revision=expected_revision,
        commit=commit,
        image=expected_image,
    )
    previous = traffic(before)
    _require(previous == traffic(after), "public traffic changed before acceptance")
    _require(
        expected_revision not in previous,
        "candidate is already receiving public traffic",
    )
    runtime_hash = check_runtime_match(revision, execution)
    status = execution.get("status", {})
    _require(
        any(
            item.get("type") == "Completed" and item.get("status") == "True"
            for item in status.get("conditions", [])
        ),
        "smoke execution did not complete successfully",
    )
    _require(
        status.get("succeededCount") == 1
        and status.get("failedCount", 0) == 0
        and status.get("cancelledCount", 0) == 0
        and status.get("retriedCount", 0) == 0,
        "smoke execution is incomplete or retried",
    )
    execution_name = _named(execution.get("metadata", {}).get("name"), "execution")
    manifest = {
        "schema_version": "rag-release-candidate-v1",
        "repository": repository,
        "commit": commit,
        "run_id": str(run_id),
        "run_attempt": str(run_attempt),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT,
        "region": REGION,
        "service": SERVICE,
        "revision": expected_revision,
        "image": expected_image,
        "tag": tag,
        "tagged_url": _tagged_url(after, tag=tag, revision=expected_revision),
        "runtime_config_sha256": runtime_hash,
        "previous_traffic": previous,
        "smoke": {
            "execution": execution_name,
            "structural_passed": True,
            "case_ids": list(CASE_IDS),
            "command": ["python", *SMOKE_ARGS],
            "scope": "same-image/config job; not the Web UI",
        },
        "semantic_review_status": "PENDING",
        "release_ready": False,
    }
    manifest["manifest_sha256"] = _hash(manifest)
    return manifest


def rollback_argument(manifest):
    values = manifest["previous_traffic"]
    _require(
        isinstance(values, dict)
        and values
        and all(type(p) is int and 0 < p <= 100 for p in values.values())
        and sum(values.values()) == 100,
        "invalid rollback traffic",
    )
    return ",".join(
        f"{_named(name, 'rollback revision')}={percent}"
        for name, percent in sorted(values.items())
    )


def validate_manifest(manifest):
    _require(
        manifest.get("schema_version") == "rag-release-candidate-v1",
        "invalid manifest schema",
    )
    _require(
        manifest.get("manifest_sha256")
        == _hash(
            {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        ),
        "manifest digest mismatch",
    )
    _require(
        (manifest.get("project"), manifest.get("region"), manifest.get("service"))
        == (PROJECT, REGION, SERVICE),
        "manifest deployment target mismatch",
    )
    _named(manifest.get("revision"), "revision")
    _named(manifest.get("tag"), "tag")
    _image(manifest.get("image"))
    _require(
        manifest.get("smoke", {}).get("structural_passed") is True
        and manifest["smoke"].get("case_ids") == list(CASE_IDS)
        and manifest["smoke"].get("command") == ["python", *SMOKE_ARGS],
        "missing complete structural smoke evidence",
    )
    rollback_argument(manifest)


def validate_promotion(manifest, review, source_run, current_service, revision):
    validate_manifest(manifest)
    _require(
        str(source_run.get("id")) == manifest["run_id"]
        and str(source_run.get("run_attempt")) == manifest["run_attempt"],
        "source run identity mismatch",
    )
    _require(
        source_run.get("status") == "completed"
        and source_run.get("conclusion") == "success",
        "source run did not succeed",
    )
    _require(
        source_run.get("head_sha") == manifest["commit"]
        and source_run.get("head_branch") == "main"
        and source_run.get("event") == "push"
        and source_run.get("path") == ".github/workflows/ci.yml"
        and source_run.get("repository", {}).get("full_name") == manifest["repository"],
        "source run provenance mismatch",
    )
    _require(
        review.get("schema_version") == "rag-release-review-v1", "invalid review schema"
    )
    for key in ("revision", "commit", "image", "manifest_sha256", "tagged_url"):
        _require(review.get(key) == manifest[key], f"review {key} mismatch")
    _require(
        str(review.get("candidate_run_id")) == manifest["run_id"]
        and str(review.get("candidate_run_attempt")) == manifest["run_attempt"],
        "review source run mismatch",
    )
    _require(
        isinstance(review.get("reviewed_by"), str) and review["reviewed_by"].strip(),
        "missing reviewer",
    )
    try:
        reviewed_at = datetime.fromisoformat(
            review.get("reviewed_at", "").replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        raise ReleaseGateError("invalid review timestamp") from None
    _require(reviewed_at.tzinfo is not None, "review timestamp requires timezone")
    cases = review.get("cases", [])
    _require(
        isinstance(cases, list)
        and len(cases) == len(CASE_IDS)
        and {case.get("case_id") for case in cases} == set(CASE_IDS),
        "manual review requires each fixed case exactly once",
    )
    _require(
        all(
            case.get("semantic") == "PASS"
            and case.get("ui") == "PASS"
            and isinstance(case.get("notes"), str)
            and case["notes"].strip()
            for case in cases
        ),
        "semantic/UI review must pass every case with evidence notes",
    )
    _require(
        traffic(current_service) == manifest["previous_traffic"],
        "public traffic changed since preparation; re-prepare/review",
    )
    _require(
        _tagged_url(current_service, tag=manifest["tag"], revision=manifest["revision"])
        == manifest["tagged_url"],
        "reviewed tagged URL changed",
    )
    _revision_check(
        revision,
        expected_revision=manifest["revision"],
        commit=manifest["commit"],
        image=manifest["image"],
    )
    _require(
        _hash(_runtime(revision)) == manifest["runtime_config_sha256"],
        "revision runtime changed since smoke",
    )
    return {
        "release_ready": True,
        "revision": manifest["revision"],
        "commit": manifest["commit"],
        "image": manifest["image"],
        "manifest_sha256": manifest["manifest_sha256"],
        "review_sha256": _hash(review),
        "traffic_argument": f"{manifest['revision']}=100",
        "rollback_argument": rollback_argument(manifest),
    }


def record_traffic_outcome(manifest, service, outcome):
    """Record actual routing, not just the already-approved traffic plan."""
    validate_manifest(manifest)
    _require(outcome in {"PROMOTED", "ROLLED_BACK"}, "invalid release outcome")
    actual = traffic(service)
    expected = (
        {manifest["revision"]: 100}
        if outcome == "PROMOTED"
        else manifest["previous_traffic"]
    )
    _require(actual == expected, "observed traffic does not match release outcome")
    return {
        "schema_version": "rag-release-outcome-v1",
        "outcome": outcome,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "revision": manifest["revision"],
        "commit": manifest["commit"],
        "manifest_sha256": manifest["manifest_sha256"],
        "observed_traffic": actual,
    }


def review_template(manifest):
    validate_manifest(manifest)
    return {
        "schema_version": "rag-release-review-v1",
        "candidate_run_id": manifest["run_id"],
        "candidate_run_attempt": manifest["run_attempt"],
        **{
            key: manifest[key]
            for key in ("revision", "commit", "image", "manifest_sha256", "tagged_url")
        },
        "reviewed_by": "",
        "reviewed_at": "",
        "cases": [
            {"case_id": key, "semantic": "PENDING", "ui": "PENDING", "notes": ""}
            for key in CASE_IDS
        ],
    }


def _load(path):
    value = json.loads(Path(path).read_text())
    _require(isinstance(value, dict), "expected a JSON object")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for key in (
        "before-service",
        "service",
        "revision",
        "execution",
        "commit",
        "run-id",
        "run-attempt",
        "repository",
        "tag",
        "expected-revision",
        "image",
        "output",
    ):
        prepare.add_argument(f"--{key}", required=True)
    check = commands.add_parser("check-runtime")
    check.add_argument("--revision", required=True)
    check.add_argument("--job", required=True)
    approval = commands.add_parser("approve")
    for key in ("manifest", "review", "source-run", "service", "revision"):
        approval.add_argument(f"--{key}", required=True)
    approval.add_argument("--output")
    template = commands.add_parser("review-template")
    template.add_argument("--manifest", required=True)
    template.add_argument("--output")
    receipt = commands.add_parser("record-traffic")
    for key in ("manifest", "service", "outcome", "output"):
        receipt.add_argument(f"--{key}", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = build_manifest(
                _load(args.before_service),
                _load(args.service),
                _load(args.revision),
                _load(args.execution),
                commit=args.commit,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                repository=args.repository,
                tag=args.tag,
                expected_revision=args.expected_revision,
                expected_image=args.image,
            )
        elif args.command == "check-runtime":
            result = {
                "runtime_config_sha256": check_runtime_match(
                    _load(args.revision), _load(args.job)
                )
            }
        elif args.command == "record-traffic":
            result = record_traffic_outcome(
                _load(args.manifest), _load(args.service), args.outcome
            )
        elif args.command == "review-template":
            result = review_template(_load(args.manifest))
        else:
            result = validate_promotion(
                _load(args.manifest),
                _load(args.review),
                _load(args.source_run),
                _load(args.service),
                _load(args.revision),
            )
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if getattr(args, "output", None):
            with Path(args.output).open("x", encoding="utf-8") as handle:
                handle.write(text)
        else:
            print(text, end="")
        return 0
    except (
        ReleaseGateError,
        KeyError,
        TypeError,
        OSError,
        ValueError,
    ) as error:
        # Never echo raw cloud config, review JSON, or exception payloads.
        message = (
            str(error) if isinstance(error, ReleaseGateError) else type(error).__name__
        )
        print(f"Release gate blocked: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
