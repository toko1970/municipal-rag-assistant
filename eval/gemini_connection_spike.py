"""Gemini one-call connection spikeを安全に実行・記録する。"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable

from langchain_google_genai import ChatGoogleGenerativeAI


MODEL = "gemini-3.1-flash-lite"
PROJECT_ID = "municipal-rag-portfolio"
SECRET_NAME = "gemini-api-key"
SECRET_VERSION = "1"
RESULT_PATH = Path("eval/results/gemini_connection_spike_phase0.json")
MAX_INPUT_TOKENS = 2_000
MAX_OUTPUT_TOKENS = 128
MAX_COST_USD = 0.01
INPUT_RATE_PER_MILLION = 0.25
OUTPUT_RATE_PER_MILLION = 1.50

EVIDENCE_TEXT = "扶養親族変更届は、事由発生日から15日以内に提出する。"
PROMPT = (
    "次の架空文書から届出期限の日数を抽出してください。\n"
    "evidence_textには架空文書を一字一句そのまま引用してください。\n"
    f"架空文書: {EVIDENCE_TEXT}"
)
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "connection_status": {"type": "string", "enum": ["ok"]},
        "deadline_days": {"type": "integer"},
        "evidence_text": {"type": "string"},
    },
    "required": ["connection_status", "deadline_days", "evidence_text"],
    "additionalProperties": False,
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * INPUT_RATE_PER_MILLION
        + output_tokens * OUTPUT_RATE_PER_MILLION
    ) / 1_000_000


def _int_value(mapping: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return int(value)
    return 0


def sanitize_error(message: str, secret: str = "") -> str:
    sanitized = message.replace(secret, "[REDACTED]") if secret else message
    sanitized = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", sanitized)
    sanitized = re.sub(
        r"(?i)(api[_ -]?key\s*[=:]\s*)\S+",
        r"\1[REDACTED]",
        sanitized,
    )
    return sanitized[:500]


def classify_error(error: Exception) -> str:
    text = f"{type(error).__name__}: {error}".lower()
    if any(marker in text for marker in ("401", "403", "unauth", "permission")):
        return "AUTH_FAILED"
    if any(
        marker in text
        for marker in ("429", "resource_exhausted", "quota", "rate limit")
    ):
        return "QUOTA_FAILED"
    return "API_FAILED"


def base_record(key_type: str, usage_tier: str, spend_cap_status: str) -> dict:
    return {
        "schema_version": "gemini-connection-spike-v1",
        "executed_at": utc_now(),
        "outcome": "LOCAL_VALIDATION_FAILED",
        "api_call_count": 0,
        "retry_count": 0,
        "requested_model": MODEL,
        "returned_model": None,
        "credential_source": "secret_manager",
        "credential_version": SECRET_VERSION,
        "key_type": key_type,
        "usage_tier": usage_tier,
        "spend_cap_status": spend_cap_status,
        "parsed_response": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "elapsed_seconds": 0.0,
        "estimated_cost_usd": 0.0,
        "pricing_observed_at": utc_now(),
        "request_id": None,
        "error_category": None,
        "error_summary": None,
    }


def validate_preflight(
    *,
    approval_confirmed: bool,
    pricing_confirmed: bool,
    key_type: str,
    usage_tier: str,
    spend_cap_status: str,
) -> str | None:
    if not approval_confirmed:
        return "user approval is not recorded"
    if not pricing_confirmed:
        return "current pricing is not confirmed"
    if key_type != "authorization":
        return "authorization key is required"
    if usage_tier not in {"free", "paid"}:
        return "usage tier is unknown"
    if usage_tier == "paid" and spend_cap_status not in {
        "configured",
        "not_configured",
    }:
        return "paid tier spend cap status is unknown"
    if usage_tier == "free" and spend_cap_status != "not_applicable":
        return "free tier spend cap status must be not_applicable"
    return None


def validate_parsed_response(parsed: Any) -> bool:
    if hasattr(parsed, "model_dump"):
        parsed = parsed.model_dump()
    return isinstance(parsed, dict) and parsed == {
        "connection_status": "ok",
        "deadline_days": 15,
        "evidence_text": EVIDENCE_TEXT,
    }


def run_spike(
    invoke_fn: Callable[[str], dict[str, Any]],
    *,
    key_type: str,
    usage_tier: str,
    spend_cap_status: str,
    secret_for_sanitizing: str = "",
    clock: Callable[[], float] = time.perf_counter,
) -> dict:
    record = base_record(key_type, usage_tier, spend_cap_status)
    started = clock()
    record["api_call_count"] = 1
    try:
        response = invoke_fn(PROMPT)
    except Exception as error:
        record["elapsed_seconds"] = round(clock() - started, 6)
        outcome = classify_error(error)
        record["outcome"] = outcome
        record["error_category"] = outcome
        record["error_summary"] = sanitize_error(
            f"{type(error).__name__}: {error}", secret_for_sanitizing
        )
        return record

    record["elapsed_seconds"] = round(clock() - started, 6)
    parsed = response.get("parsed")
    if hasattr(parsed, "model_dump"):
        parsed = parsed.model_dump()
    record["parsed_response"] = parsed

    usage = dict(response.get("usage_metadata") or {})
    metadata = dict(response.get("response_metadata") or {})
    input_tokens = _int_value(usage, "input_tokens", "prompt_token_count")
    output_tokens = _int_value(usage, "output_tokens", "candidates_token_count")
    total_tokens = _int_value(usage, "total_tokens", "total_token_count")
    record.update(
        {
            "returned_model": metadata.get("model_name") or MODEL,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens or input_tokens + output_tokens,
            "estimated_cost_usd": estimate_cost_usd(input_tokens, output_tokens),
            "request_id": metadata.get("response_id") or None,
        }
    )

    if not validate_parsed_response(parsed):
        record["outcome"] = "SCHEMA_OR_VALUE_FAILED"
        record["error_category"] = "SCHEMA_OR_VALUE_FAILED"
        record["error_summary"] = "structured response did not match fixed values"
    elif input_tokens <= 0 or output_tokens <= 0:
        record["outcome"] = "USAGE_METADATA_MISSING"
        record["error_category"] = "USAGE_METADATA_MISSING"
        record["error_summary"] = "input or output token usage was missing"
    elif record["estimated_cost_usd"] > MAX_COST_USD:
        record["outcome"] = "COST_LIMIT_EXCEEDED"
        record["error_category"] = "COST_LIMIT_EXCEEDED"
        record["error_summary"] = "estimated cost exceeded the fixed limit"
    else:
        record["outcome"] = "SUCCESS"
    return record


def build_invoke_fn(
    api_key: str,
    model_factory: Callable[..., Any] = ChatGoogleGenerativeAI,
) -> Callable[[str], dict[str, Any]]:
    model = model_factory(
        model=MODEL,
        api_key=api_key,
        temperature=0,
        max_tokens=MAX_OUTPUT_TOKENS,
        retries=0,
        request_timeout=60,
        thinking_level="minimal",
    )
    structured = model.with_structured_output(
        RESPONSE_SCHEMA,
        method="json_schema",
        include_raw=True,
    )

    def invoke(prompt: str) -> dict[str, Any]:
        result = structured.invoke(prompt)
        raw = result.get("raw")
        return {
            "parsed": result.get("parsed"),
            "usage_metadata": getattr(raw, "usage_metadata", None),
            "response_metadata": getattr(raw, "response_metadata", None),
        }

    return invoke


def load_secret_from_gcloud() -> str:
    completed = subprocess.run(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            SECRET_VERSION,
            f"--secret={SECRET_NAME}",
            f"--project={PROJECT_ID}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    secret = completed.stdout.strip()
    if not secret:
        raise RuntimeError("Secret Manager returned an empty payload")
    return secret


def save_record(record: dict, path: Path = RESULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def dry_run_record() -> dict:
    projected_cost = estimate_cost_usd(MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS)
    return {
        "outcome": "DRY_RUN_OK" if projected_cost < MAX_COST_USD else "COST_GATE_FAILED",
        "api_call_count": 0,
        "retry_count": 0,
        "requested_model": MODEL,
        "projected_max_cost_usd": projected_cost,
        "cost_limit_usd": MAX_COST_USD,
        "secret_accessed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--key-type",
        choices=("authorization", "standard", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--usage-tier", choices=("free", "paid", "unknown"), default="unknown"
    )
    parser.add_argument(
        "--spend-cap-status",
        choices=("configured", "not_configured", "not_applicable", "unknown"),
        default="unknown",
    )
    parser.add_argument("--pricing-confirmed", action="store_true")
    parser.add_argument("--approval-confirmed", action="store_true")
    parser.add_argument("--output", type=Path, default=RESULT_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        print(json.dumps(dry_run_record(), ensure_ascii=False, indent=2))
        return 0

    blocked_reason = validate_preflight(
        approval_confirmed=args.approval_confirmed,
        pricing_confirmed=args.pricing_confirmed,
        key_type=args.key_type,
        usage_tier=args.usage_tier,
        spend_cap_status=args.spend_cap_status,
    )
    if blocked_reason:
        record = base_record(args.key_type, args.usage_tier, args.spend_cap_status)
        record["outcome"] = "BLOCKED_KEY_METADATA"
        record["error_category"] = "BLOCKED_KEY_METADATA"
        record["error_summary"] = blocked_reason
        save_record(record, args.output)
        return 2

    secret = ""
    try:
        secret = load_secret_from_gcloud()
        invoke = build_invoke_fn(secret)
    except Exception as error:
        record = base_record(args.key_type, args.usage_tier, args.spend_cap_status)
        record["error_summary"] = sanitize_error(
            f"{type(error).__name__}: {error}", secret
        )
        save_record(record, args.output)
        return 2

    record = run_spike(
        invoke,
        key_type=args.key_type,
        usage_tier=args.usage_tier,
        spend_cap_status=args.spend_cap_status,
        secret_for_sanitizing=secret,
    )
    save_record(record, args.output)
    return 0 if record["outcome"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
