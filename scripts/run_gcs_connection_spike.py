"""Run the bounded Phase 0 GCS connection spike.

The script creates one short-lived bucket and one fictional object. It grants
the active developer account service-account impersonation only for the spike,
then removes that binding during cleanup. It never prints or stores an access
token or the developer account name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ID = "municipal-rag-portfolio"
REGION = "asia-northeast1"
BUCKET_NAME = "municipal-rag-portfolio-phase0-spike-280649014820"
BUCKET_URL = f"gs://{BUCKET_NAME}"
RUNTIME_IDENTITY = (
    "municipal-rag-runtime@municipal-rag-portfolio.iam.gserviceaccount.com"
)
OBJECT_PATH = "spike/gcs-connection/v1/payload.json"
OBJECT_URL = f"{BUCKET_URL}/{OBJECT_PATH}"
EXPECTED_SHA256 = "87bf4ff37425748dfe97869eef5253f163440d2927b953ace680d92c98c70448"
EXPECTED_SIZE = 131
ESTIMATED_OPERATION_COST_USD = 0.000054
IMPERSONATION_CHECK_ATTEMPTS = 12
IMPERSONATION_CHECK_INTERVAL_SECONDS = 10
BUCKET_ACCESS_CHECK_ATTEMPTS = 4
BUCKET_ACCESS_CHECK_INTERVAL_SECONDS = 10
PAYLOAD = (
    '{"document_id":"gcs-spike-001","title":"架空給与通知",'
    '"content":"この文書は接続試験用の架空データです。"}\n'
).encode()
RESULT_PATH = (
    Path(__file__).resolve().parents[1]
    / "eval"
    / "results"
    / "gcs_connection_spike_phase0.json"
)


class SpikeFailure(RuntimeError):
    """Expected terminal failure with a safe public summary."""

    def __init__(self, category: str, summary: str) -> None:
        super().__init__(summary)
        self.category = category
        self.summary = summary


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command while retaining output for validation, not display."""
    return subprocess.run(args, check=False, capture_output=True, text=True)


def require_success(
    args: list[str], category: str, summary: str
) -> subprocess.CompletedProcess[str]:
    completed = run(args)
    if completed.returncode != 0:
        raise SpikeFailure(category, summary)
    return completed


def is_not_found(completed: subprocess.CompletedProcess[str]) -> bool:
    output = f"{completed.stdout}\n{completed.stderr}".lower()
    return completed.returncode != 0 and (
        "404" in output or "not found" in output or "does not exist" in output
    )


def base_result() -> dict[str, Any]:
    return {
        "schema_version": "gcs-connection-spike-v1",
        "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "outcome": "LOCAL_VALIDATION_FAILED",
        "project_id": PROJECT_ID,
        "region": REGION,
        "bucket_name": BUCKET_NAME,
        "runtime_identity": RUNTIME_IDENTITY,
        "bucket_settings_verified": False,
        "object_path": OBJECT_PATH,
        "object_generation": None,
        "size_bytes": EXPECTED_SIZE,
        "expected_sha256": EXPECTED_SHA256,
        "downloaded_sha256": None,
        "round_trip_seconds": 0.0,
        "application_attempts": {
            "temporary_token_creator_grant": 0,
            "impersonation": 0,
            "bucket_create": 0,
            "bucket_iam_grant": 0,
            "bucket_access_check": 0,
            "upload": 0,
            "metadata_get": 0,
            "download": 0,
            "object_delete": 0,
            "bucket_delete": 0,
            "temporary_token_creator_remove": 0,
        },
        "estimated_operation_cost_usd": 0.0,
        "object_absence_verified": False,
        "bucket_absence_verified": False,
        "temporary_token_creator_removed": False,
        "error_category": None,
        "error_summary": None,
    }


def write_result(result: dict[str, Any]) -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RESULT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(RESULT_PATH)


def validate_local_payload() -> None:
    if len(PAYLOAD) != EXPECTED_SIZE:
        raise SpikeFailure("LOCAL_VALIDATION_FAILED", "Payload size changed.")
    if hashlib.sha256(PAYLOAD).hexdigest() != EXPECTED_SHA256:
        raise SpikeFailure("LOCAL_VALIDATION_FAILED", "Payload SHA-256 changed.")


def active_account() -> str:
    completed = require_success(
        [
            "gcloud",
            "auth",
            "list",
            "--filter=status:ACTIVE",
            "--format=value(account)",
        ],
        "LOCAL_VALIDATION_FAILED",
        "The active gcloud account could not be read.",
    )
    accounts = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(accounts) != 1:
        raise SpikeFailure(
            "LOCAL_VALIDATION_FAILED", "Exactly one active gcloud account is required."
        )
    return accounts[0]


def validate_bucket_settings(settings: dict[str, Any]) -> None:
    failures: list[str] = []
    if settings.get("name") != BUCKET_NAME:
        failures.append("name")
    if str(settings.get("location", "")).upper() != REGION.upper():
        failures.append("location")
    if settings.get("default_storage_class") != "STANDARD":
        failures.append("default_storage_class")
    if settings.get("uniform_bucket_level_access") is not True:
        failures.append("uniform_bucket_level_access")
    if settings.get("public_access_prevention") != "enforced":
        failures.append("public_access_prevention")

    soft_delete = settings.get("soft_delete_policy")
    if soft_delete and str(soft_delete.get("retentionDurationSeconds", "0")) != "0":
        failures.append("soft_delete_policy")
    if settings.get("versioning_enabled") is True:
        failures.append("versioning_enabled")
    if settings.get("retention_policy"):
        failures.append("retention_policy")
    autoclass = settings.get("autoclass")
    if autoclass and autoclass.get("enabled") is True:
        failures.append("autoclass")
    if failures:
        raise SpikeFailure(
            "BUCKET_CONFIGURATION_FAILED",
            "Unexpected bucket settings: " + ", ".join(failures),
        )


def describe_object() -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    completed = run(
        [
            "gcloud",
            "storage",
            "objects",
            "describe",
            OBJECT_URL,
            f"--impersonate-service-account={RUNTIME_IDENTITY}",
            "--raw",
            "--format=json",
        ]
    )
    if completed.returncode != 0:
        return completed, None
    return completed, json.loads(completed.stdout)


def remove_token_creator(account: str) -> bool:
    completed = run(
        [
            "gcloud",
            "iam",
            "service-accounts",
            "remove-iam-policy-binding",
            RUNTIME_IDENTITY,
            f"--project={PROJECT_ID}",
            f"--member=user:{account}",
            "--role=roles/iam.serviceAccountTokenCreator",
            "--quiet",
        ]
    )
    return completed.returncode == 0


def cleanup(
    result: dict[str, Any], account: str | None, token_binding_added: bool
) -> list[str]:
    errors: list[str] = []
    bucket_check = run(
        [
            "gcloud",
            "storage",
            "buckets",
            "describe",
            BUCKET_URL,
            f"--project={PROJECT_ID}",
            "--format=value(name)",
        ]
    )
    if bucket_check.returncode == 0:
        listed = run(["gcloud", "storage", "ls", f"{BUCKET_URL}/**", "--recursive"])
        no_match = "matched no objects" in listed.stderr.lower()
        objects = [
            line.strip()
            for line in listed.stdout.splitlines()
            if line.strip().startswith("gs://") and not line.strip().endswith("/")
        ]
        if listed.returncode != 0 and not no_match:
            errors.append("bucket content listing failed")
        unexpected = [object_url for object_url in objects if object_url != OBJECT_URL]
        if unexpected:
            errors.append("unexpected object found; bucket retained")

        if OBJECT_URL in objects and not errors:
            metadata_completed = run(
                [
                    "gcloud",
                    "storage",
                    "objects",
                    "describe",
                    OBJECT_URL,
                    "--raw",
                    "--format=json",
                ]
            )
            if metadata_completed.returncode != 0:
                errors.append("fixed object generation unavailable")
            else:
                try:
                    metadata = json.loads(metadata_completed.stdout)
                except json.JSONDecodeError:
                    metadata = {}
                generation = str(metadata.get("generation", ""))
                if not generation:
                    errors.append("fixed object generation unavailable")
                else:
                    deleted = run(
                        [
                            "gcloud",
                            "storage",
                            "rm",
                            OBJECT_URL,
                            f"--if-generation-match={generation}",
                            "--quiet",
                        ]
                    )
                    if deleted.returncode != 0:
                        errors.append("fixed object cleanup failed")

        if not errors:
            deleted_bucket = run(
                [
                    "gcloud",
                    "storage",
                    "buckets",
                    "delete",
                    BUCKET_URL,
                    f"--project={PROJECT_ID}",
                    "--quiet",
                ]
            )
            if deleted_bucket.returncode != 0:
                errors.append("bucket cleanup failed")

    final_bucket_check = run(
        [
            "gcloud",
            "storage",
            "buckets",
            "describe",
            BUCKET_URL,
            f"--project={PROJECT_ID}",
            "--format=value(name)",
        ]
    )
    result["bucket_absence_verified"] = is_not_found(final_bucket_check)
    if result["bucket_absence_verified"]:
        result["object_absence_verified"] = True

    if token_binding_added and account:
        result["application_attempts"]["temporary_token_creator_remove"] += 1
        result["temporary_token_creator_removed"] = remove_token_creator(account)
        if not result["temporary_token_creator_removed"]:
            errors.append("temporary Token Creator binding cleanup failed")
    return errors


def execute() -> dict[str, Any]:
    result = base_result()
    account: str | None = None
    token_binding_added = False
    completed_successfully = False
    started = time.monotonic()

    try:
        validate_local_payload()
        account = active_account()

        bucket_preflight = run(
            [
                "gcloud",
                "storage",
                "buckets",
                "describe",
                BUCKET_URL,
                f"--project={PROJECT_ID}",
                "--format=value(name)",
            ]
        )
        if bucket_preflight.returncode == 0:
            raise SpikeFailure(
                "BLOCKED_BUCKET_EXISTS", "The fixed spike bucket already exists."
            )
        if not is_not_found(bucket_preflight):
            raise SpikeFailure(
                "LOCAL_VALIDATION_FAILED", "Bucket absence could not be verified."
            )

        result["application_attempts"]["temporary_token_creator_grant"] += 1
        require_success(
            [
                "gcloud",
                "iam",
                "service-accounts",
                "add-iam-policy-binding",
                RUNTIME_IDENTITY,
                f"--project={PROJECT_ID}",
                f"--member=user:{account}",
                "--role=roles/iam.serviceAccountTokenCreator",
                "--quiet",
            ],
            "IAM_FAILED",
            "Temporary Token Creator binding could not be added.",
        )
        token_binding_added = True

        impersonation_ready = False
        for attempt in range(IMPERSONATION_CHECK_ATTEMPTS):
            result["application_attempts"]["impersonation"] += 1
            token_check = run(
                [
                    "gcloud",
                    "auth",
                    "print-access-token",
                    f"--impersonate-service-account={RUNTIME_IDENTITY}",
                    "--quiet",
                ]
            )
            if token_check.returncode == 0:
                impersonation_ready = True
                break
            if attempt < IMPERSONATION_CHECK_ATTEMPTS - 1:
                time.sleep(IMPERSONATION_CHECK_INTERVAL_SECONDS)
        if not impersonation_ready:
            raise SpikeFailure(
                "BLOCKED_IMPERSONATION",
                    "Runtime service account impersonation was not ready within the two-minute propagation window.",
            )

        with tempfile.TemporaryDirectory(prefix="gcs-connection-spike-") as directory:
            source = Path(directory) / "payload.json"
            downloaded = Path(directory) / "downloaded.json"
            source.write_bytes(PAYLOAD)

            result["application_attempts"]["bucket_create"] += 1
            require_success(
                [
                    "gcloud",
                    "storage",
                    "buckets",
                    "create",
                    BUCKET_URL,
                    f"--project={PROJECT_ID}",
                    f"--location={REGION}",
                    "--default-storage-class=STANDARD",
                    "--uniform-bucket-level-access",
                    "--public-access-prevention",
                    "--soft-delete-duration=0",
                    "--quiet",
                ],
                "BUCKET_CONFIGURATION_FAILED",
                "The short-lived bucket could not be created.",
            )

            described = require_success(
                [
                    "gcloud",
                    "storage",
                    "buckets",
                    "describe",
                    BUCKET_URL,
                    f"--project={PROJECT_ID}",
                    "--format=json",
                ],
                "BUCKET_CONFIGURATION_FAILED",
                "The created bucket settings could not be read.",
            )
            validate_bucket_settings(json.loads(described.stdout))
            result["bucket_settings_verified"] = True

            result["application_attempts"]["bucket_iam_grant"] += 1
            require_success(
                [
                    "gcloud",
                    "storage",
                    "buckets",
                    "add-iam-policy-binding",
                    BUCKET_URL,
                    f"--member=serviceAccount:{RUNTIME_IDENTITY}",
                    "--role=roles/storage.objectUser",
                    "--quiet",
                ],
                "IAM_FAILED",
                "Bucket-scoped objectUser binding could not be added.",
            )

            bucket_access_ready = False
            for attempt in range(BUCKET_ACCESS_CHECK_ATTEMPTS):
                result["application_attempts"]["bucket_access_check"] += 1
                access_check = run(
                    [
                        "gcloud",
                        "storage",
                        "ls",
                        BUCKET_URL,
                        f"--impersonate-service-account={RUNTIME_IDENTITY}",
                    ]
                )
                if access_check.returncode == 0:
                    bucket_access_ready = True
                    break
                if attempt < BUCKET_ACCESS_CHECK_ATTEMPTS - 1:
                    time.sleep(BUCKET_ACCESS_CHECK_INTERVAL_SECONDS)
            if not bucket_access_ready:
                raise SpikeFailure(
                    "IAM_FAILED",
                    "Runtime bucket access was not ready within the bounded propagation window.",
                )

            round_trip_started = time.monotonic()
            result["application_attempts"]["upload"] += 1
            require_success(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    str(source),
                    OBJECT_URL,
                    "--content-type=application/json",
                    f"--custom-metadata=sha256={EXPECTED_SHA256}",
                    "--if-generation-match=0",
                    f"--impersonate-service-account={RUNTIME_IDENTITY}",
                    "--quiet",
                ],
                "UPLOAD_FAILED",
                "The conditional upload failed.",
            )

            result["application_attempts"]["metadata_get"] += 1
            metadata_completed, metadata = describe_object()
            if metadata is None:
                raise SpikeFailure("METADATA_FAILED", "Object metadata could not be read.")
            generation = str(metadata.get("generation", ""))
            size = int(metadata.get("size", -1))
            content_type = metadata.get("contentType") or metadata.get("content_type")
            custom_metadata = metadata.get("metadata") or metadata.get("custom_metadata") or {}
            if (
                not generation
                or size != EXPECTED_SIZE
                or content_type != "application/json"
                or custom_metadata.get("sha256") != EXPECTED_SHA256
            ):
                raise SpikeFailure(
                    "METADATA_FAILED", "Object generation, size, type, or SHA metadata differed."
                )
            result["object_generation"] = generation

            result["application_attempts"]["download"] += 1
            require_success(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    f"{OBJECT_URL}#{generation}",
                    str(downloaded),
                    f"--impersonate-service-account={RUNTIME_IDENTITY}",
                    "--quiet",
                ],
                "DOWNLOAD_FAILED",
                "The explicit-generation download failed.",
            )
            downloaded_sha256 = hashlib.sha256(downloaded.read_bytes()).hexdigest()
            result["downloaded_sha256"] = downloaded_sha256
            if downloaded_sha256 != EXPECTED_SHA256:
                raise SpikeFailure("HASH_MISMATCH", "The downloaded SHA-256 differed.")

            result["application_attempts"]["object_delete"] += 1
            require_success(
                [
                    "gcloud",
                    "storage",
                    "rm",
                    OBJECT_URL,
                    f"--if-generation-match={generation}",
                    f"--impersonate-service-account={RUNTIME_IDENTITY}",
                    "--quiet",
                ],
                "DELETE_FAILED",
                "The generation-matched object delete failed.",
            )
            absence_check, _ = describe_object()
            result["object_absence_verified"] = is_not_found(absence_check)
            if not result["object_absence_verified"]:
                raise SpikeFailure("DELETE_FAILED", "Object absence could not be verified.")

            result["application_attempts"]["bucket_delete"] += 1
            require_success(
                [
                    "gcloud",
                    "storage",
                    "buckets",
                    "delete",
                    BUCKET_URL,
                    f"--project={PROJECT_ID}",
                    "--quiet",
                ],
                "CLEANUP_INCOMPLETE",
                "The empty spike bucket could not be deleted.",
            )
            bucket_absence = run(
                [
                    "gcloud",
                    "storage",
                    "buckets",
                    "describe",
                    BUCKET_URL,
                    f"--project={PROJECT_ID}",
                    "--format=value(name)",
                ]
            )
            result["bucket_absence_verified"] = is_not_found(bucket_absence)
            if not result["bucket_absence_verified"]:
                raise SpikeFailure(
                    "CLEANUP_INCOMPLETE", "Bucket absence could not be verified."
                )

            result["round_trip_seconds"] = round(time.monotonic() - round_trip_started, 3)
            result["estimated_operation_cost_usd"] = ESTIMATED_OPERATION_COST_USD
            completed_successfully = True

    except SpikeFailure as error:
        result["outcome"] = error.category
        result["error_category"] = error.category
        result["error_summary"] = error.summary
    except (json.JSONDecodeError, OSError, ValueError) as error:
        result["outcome"] = "LOCAL_VALIDATION_FAILED"
        result["error_category"] = "LOCAL_VALIDATION_FAILED"
        result["error_summary"] = type(error).__name__
    finally:
        cleanup_errors = cleanup(result, account, token_binding_added)
        if cleanup_errors:
            result["outcome"] = "CLEANUP_INCOMPLETE"
            result["error_category"] = "CLEANUP_INCOMPLETE"
            result["error_summary"] = "; ".join(cleanup_errors)
        elif completed_successfully:
            result["outcome"] = "SUCCESS"
            result["error_category"] = None
            result["error_summary"] = None
        result["executed_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        result["total_seconds"] = round(time.monotonic() - started, 3)
        write_result(result)
    return result


def dry_run() -> None:
    validate_local_payload()
    print(
        json.dumps(
            {
                "project_id": PROJECT_ID,
                "bucket_name": BUCKET_NAME,
                "runtime_identity": RUNTIME_IDENTITY,
                "payload_size": EXPECTED_SIZE,
                "payload_sha256": EXPECTED_SHA256,
                "cost_limit_usd": 0.01,
                "estimated_operation_cost_usd": ESTIMATED_OPERATION_COST_USD,
                "temporary_iam_binding": "roles/iam.serviceAccountTokenCreator",
                "bucket_iam_binding": "roles/storage.objectUser",
                "cleanup": [
                    "delete fixed object generation",
                    "delete short-lived bucket",
                    "remove temporary Token Creator binding",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        dry_run()
        return 0
    result = execute()
    print(f"outcome={result['outcome']}")
    print(f"bucket_absence_verified={result['bucket_absence_verified']}")
    print(
        "temporary_token_creator_removed="
        f"{result['temporary_token_creator_removed']}"
    )
    return 0 if result["outcome"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
