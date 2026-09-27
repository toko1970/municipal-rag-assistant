from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eval.gemini_connection_spike import (
    EVIDENCE_TEXT,
    MAX_COST_USD,
    PROMPT,
    build_invoke_fn,
    dry_run_record,
    estimate_cost_usd,
    main,
    run_spike,
    sanitize_error,
    validate_preflight,
)


def success_response(input_tokens=100, output_tokens=20):
    return {
        "parsed": {
            "connection_status": "ok",
            "deadline_days": 15,
            "evidence_text": EVIDENCE_TEXT,
        },
        "usage_metadata": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        "response_metadata": {
            "model_name": "gemini-3.1-flash-lite",
            "response_id": "response-1",
        },
    }


class CountingInvoker:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    def __call__(self, _prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


class GeminiConnectionSpikeTest(unittest.TestCase):
    def test_dry_run_does_not_access_secret_or_call_api(self):
        record = dry_run_record()

        self.assertEqual(record["outcome"], "DRY_RUN_OK")
        self.assertEqual(record["api_call_count"], 0)
        self.assertFalse(record["secret_accessed"])
        self.assertLess(record["projected_max_cost_usd"], MAX_COST_USD)

    def test_success_calls_provider_exactly_once(self):
        invoker = CountingInvoker(response=success_response())

        record = run_spike(
            invoker,
            key_type="authorization",
            usage_tier="paid",
            spend_cap_status="configured",
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(record["api_call_count"], 1)
        self.assertEqual(record["retry_count"], 0)
        self.assertEqual(record["outcome"], "SUCCESS")
        self.assertEqual(record["request_id"], "response-1")
        self.assertAlmostEqual(record["estimated_cost_usd"], 0.000055)

    def test_preflight_blocks_unknown_or_standard_key_without_calling_api(self):
        self.assertEqual(
            validate_preflight(
                approval_confirmed=True,
                pricing_confirmed=True,
                key_type="standard",
                usage_tier="free",
                spend_cap_status="not_applicable",
            ),
            "authorization key is required",
        )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "blocked.json"
            with patch(
                "eval.gemini_connection_spike.load_secret_from_gcloud",
                side_effect=AssertionError("secret access must not happen"),
            ) as secret_loader:
                exit_code = main(
                    [
                        "--execute",
                        "--key-type",
                        "standard",
                        "--usage-tier",
                        "free",
                        "--spend-cap-status",
                        "not_applicable",
                        "--pricing-confirmed",
                        "--approval-confirmed",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 2)
            secret_loader.assert_not_called()
            self.assertIn('"api_call_count": 0', output.read_text(encoding="utf-8"))

    def test_client_initialization_error_does_not_write_secret(self):
        secret = "test-secret-client-initialization"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "client-error.json"
            with (
                patch(
                    "eval.gemini_connection_spike.load_secret_from_gcloud",
                    return_value=secret,
                ),
                patch(
                    "eval.gemini_connection_spike.build_invoke_fn",
                    side_effect=RuntimeError(f"invalid api_key={secret}"),
                ),
            ):
                exit_code = main(
                    [
                        "--execute",
                        "--key-type",
                        "authorization",
                        "--usage-tier",
                        "free",
                        "--spend-cap-status",
                        "not_applicable",
                        "--pricing-confirmed",
                        "--approval-confirmed",
                        "--output",
                        str(output),
                    ]
                )

            result_text = output.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 2)
            self.assertNotIn(secret, result_text)
            self.assertIn("[REDACTED]", result_text)

    def test_authentication_error_is_sanitized_and_not_retried(self):
        secret = "test-secret-authentication"
        invoker = CountingInvoker(error=RuntimeError(f"401 api_key={secret}"))

        record = run_spike(
            invoker,
            key_type="authorization",
            usage_tier="free",
            spend_cap_status="not_applicable",
            secret_for_sanitizing=secret,
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(record["outcome"], "AUTH_FAILED")
        self.assertNotIn(secret, record["error_summary"])
        self.assertIn("[REDACTED]", record["error_summary"])

    def test_quota_error_is_not_retried(self):
        invoker = CountingInvoker(error=RuntimeError("429 RESOURCE_EXHAUSTED"))

        record = run_spike(
            invoker,
            key_type="authorization",
            usage_tier="free",
            spend_cap_status="not_applicable",
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(record["outcome"], "QUOTA_FAILED")

    def test_schema_or_fixed_value_mismatch_stops_after_one_call(self):
        response = success_response()
        response["parsed"]["deadline_days"] = 14
        invoker = CountingInvoker(response=response)

        record = run_spike(
            invoker,
            key_type="authorization",
            usage_tier="free",
            spend_cap_status="not_applicable",
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(record["outcome"], "SCHEMA_OR_VALUE_FAILED")

    def test_missing_usage_metadata_stops_after_one_call(self):
        response = success_response(input_tokens=0, output_tokens=0)
        invoker = CountingInvoker(response=response)

        record = run_spike(
            invoker,
            key_type="authorization",
            usage_tier="free",
            spend_cap_status="not_applicable",
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(record["outcome"], "USAGE_METADATA_MISSING")

    def test_cost_limit_exceeded_stops_after_one_call(self):
        response = success_response(input_tokens=50_000, output_tokens=1)
        invoker = CountingInvoker(response=response)

        record = run_spike(
            invoker,
            key_type="authorization",
            usage_tier="paid",
            spend_cap_status="not_configured",
        )

        self.assertEqual(invoker.calls, 1)
        self.assertEqual(record["outcome"], "COST_LIMIT_EXCEEDED")
        self.assertGreater(record["estimated_cost_usd"], MAX_COST_USD)

    def test_langchain_client_disables_retries_and_uses_fixed_schema(self):
        captured = {}

        class FakeRaw:
            usage_metadata = {"input_tokens": 10, "output_tokens": 5}
            response_metadata = {"model_name": "gemini-3.1-flash-lite"}

        class FakeStructured:
            def invoke(self, prompt):
                captured["prompt"] = prompt
                return {"raw": FakeRaw(), "parsed": success_response()["parsed"]}

        class FakeModel:
            def __init__(self, **kwargs):
                captured["model_kwargs"] = kwargs

            def with_structured_output(self, schema, **kwargs):
                captured["schema"] = schema
                captured["structured_kwargs"] = kwargs
                return FakeStructured()

        invoke = build_invoke_fn("test-secret", model_factory=FakeModel)
        response = invoke(PROMPT)

        self.assertEqual(captured["model_kwargs"]["retries"], 0)
        self.assertEqual(captured["model_kwargs"]["request_timeout"], 60)
        self.assertEqual(captured["model_kwargs"]["max_tokens"], 128)
        self.assertEqual(captured["structured_kwargs"]["method"], "json_schema")
        self.assertTrue(captured["structured_kwargs"]["include_raw"])
        self.assertEqual(response["usage_metadata"]["input_tokens"], 10)

    def test_cost_formula_and_generic_key_pattern_sanitizer(self):
        self.assertAlmostEqual(estimate_cost_usd(2_000, 128), 0.000692)
        sanitized = sanitize_error("api_key=unsafe-value")
        self.assertNotIn("unsafe-value", sanitized)


if __name__ == "__main__":
    unittest.main()
