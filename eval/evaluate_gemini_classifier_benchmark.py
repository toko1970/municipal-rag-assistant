"""Evaluate the production Gemini classifier on the fixed 36-case benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME
from eval.evaluate_local_nli_classifier import summarize
from eval.evaluate_visual_answers import token_cost_usd
from src.answering import parse_classification_output
from src.llm_provider import GeminiProvider
from src.query_service import build_classification_prompt_v1_from_payload, load_schema


DEFAULT_DATASET = BASE_DIR / "eval/classifier_model_benchmark_v1.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
RESERVE_USD_PER_CALL = 0.0013


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def run(
    *,
    dataset_path: Path,
    output_path: Path,
    max_logical_external_calls: int,
    max_cost_usd: float,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"結果は上書きしません: {output_path}")
    dataset = load_json(dataset_path)
    cases = dataset["cases"]
    if dataset.get("review_status") != "approved":
        raise ValueError("approved benchmarkだけを評価できます")
    if max_logical_external_calls != len(cases):
        raise ValueError(f"logical external call上限は{len(cases)}で固定します")
    if max_cost_usd < len(cases) * RESERVE_USD_PER_CALL:
        raise ValueError("cost上限が全callの予約額を下回っています")

    provider = GeminiProvider(CLASSIFIER_MODEL_NAME)
    schema = load_schema(CLASSIFICATION_SCHEMA)
    records = []
    factor_records = []
    input_tokens = 0
    output_tokens = 0
    started = time.perf_counter()
    for case in cases:
        if (
            token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_CALL
            > max_cost_usd
        ):
            raise RuntimeError("cost上限へ達する前に比較を完了できません")
        case_started = time.perf_counter()
        try:
            response = provider.generate_structured(
                build_classification_prompt_v1_from_payload(
                    case["question"], case["evidence"], case["generated_answer"]
                ),
                schema,
            )
            parsed = parse_classification_output(response.data)
        except Exception as exception:
            failure = {
                "schema_version": "1.0",
                "status": "FAILED",
                "model": CLASSIFIER_MODEL_NAME,
                "retry_count": 0,
                "max_logical_external_calls": max_logical_external_calls,
                "max_cost_usd": max_cost_usd,
                "completed_calls": len(records),
                "error": f"{type(exception).__name__}: {exception}",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
                "external_api_calls": len(records) + 1,
                "sealed_holdout_used": False,
                "records": records,
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return failure
        input_tokens += response.input_tokens
        output_tokens += response.output_tokens
        predicted = vars(parsed.factors)
        records.append(
            {
                "case_id": case["case_id"],
                "seconds": time.perf_counter() - case_started,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "request_id": response.request_id,
                "confidence": parsed.confidence,
                "response": response.data,
            }
        )
        factor_records.extend(
            {
                "case_id": case["case_id"],
                "factor": factor,
                "predicted": value,
            }
            for factor, value in predicted.items()
        )
        print(f"completed_calls={len(records)}/{len(cases)}", flush=True)

    result = {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "model": CLASSIFIER_MODEL_NAME,
        "dataset": str(dataset_path.relative_to(BASE_DIR)),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "retry_count": 0,
        "max_logical_external_calls": max_logical_external_calls,
        "max_cost_usd": max_cost_usd,
        "external_api_calls": len(records),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "elapsed_seconds": time.perf_counter() - started,
        "sealed_holdout_used": False,
        "summary": summarize(cases, factor_records),
        "records": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    result = run(
        dataset_path=args.dataset.resolve(),
        output_path=args.output.resolve(),
        max_logical_external_calls=args.max_logical_external_calls,
        max_cost_usd=args.max_cost_usd,
    )
    fields = ("status", "external_api_calls", "estimated_cost_usd")
    print(json.dumps({key: result.get(key) for key in fields}, ensure_ascii=False))
    return 0 if result["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
