"""Bounded impact pilot for the date-only answer-output-v1.1 route."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME
from eval.compare_answer_contract_v2 import PilotLogger, SCENARIOS, StaticIndex, _element
from eval.evaluate_visual_answers import token_cost_usd
from eval.run_text_holdout_predictions import (
    ExternalCallBudget,
    PacedProvider,
    SharedCallPacer,
)
from src.contracts import SearchHit
from src.llm_provider import GeminiProvider
from src.query_service import (
    DEADLINE_CLASSIFICATION_PROMPT_VERSION,
    answer_question,
    build_deadline_classification_prompt,
    load_schema,
)
from src.temporal_evidence import (
    DEADLINE_CALCULATION_PROMPT_VERSION,
    build_deadline_calculation_prompt,
)


ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
SCENARIO_IDS = (
    "ACV2-D01",
    "ACV2-D02",
    "ACV2-D03",
    "ACV2-D04",
    "ACV2-D05",
    "ACV2-D06",
    "ACV2-C01",
    "ACV2-C02",
)
MAX_LOGICAL_EXTERNAL_CALLS = len(SCENARIO_IDS) * 2
RESERVE_USD_PER_SCENARIO = 0.0015


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _content_ok(answer: str, patterns: tuple[str, ...]) -> bool:
    return all(re.search(pattern, answer) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_logical_external_calls > MAX_LOGICAL_EXTERNAL_CALLS:
        raise ValueError("logical external call上限は16です")
    if args.max_cost_usd < len(SCENARIO_IDS) * RESERVE_USD_PER_SCENARIO:
        raise ValueError("費用上限が8件の安全予約額を下回っています")

    scenarios = [row for row in SCENARIOS if row["id"] in SCENARIO_IDS]
    args.output_dir.mkdir(parents=True)
    _write_json(
        args.output_dir / "run_manifest.json",
        {
            "experiment": "deadline-calculation-v1.1-impact-pilot-v1",
            "scenario_ids": list(SCENARIO_IDS),
            "generator_model": LLM_MODEL_NAME,
            "classifier_model": CLASSIFIER_MODEL_NAME,
            "answer_schema": str(ANSWER_SCHEMA.relative_to(BASE_DIR)),
            "generation_prompt_version": DEADLINE_CALCULATION_PROMPT_VERSION,
            "classification_prompt_version": DEADLINE_CLASSIFICATION_PROMPT_VERSION,
            "max_logical_external_calls": args.max_logical_external_calls,
            "provider_retry_policy": {
                "max_retries": 2,
                "retryable_status_codes": [503],
                "minimum_call_interval_seconds": 5.1,
                "backoff_seconds": [5.1, 10.2],
                "jitter_max_seconds": 1.0
            },
            "max_cost_usd": args.max_cost_usd,
            "sealed_holdout_accessed": False,
            "production_deployed": False,
        },
    )
    budget = ExternalCallBudget(args.max_logical_external_calls)
    pacer = SharedCallPacer(5.1)

    def provider(model: str) -> PacedProvider:
        return PacedProvider(
            GeminiProvider(model),
            pacer,
            budget,
            max_retries=2,
            backoff_initial_seconds=5.1,
            backoff_max_seconds=10.2,
            jitter_max_seconds=1.0,
        )

    generator = provider(LLM_MODEL_NAME)
    classifier = provider(CLASSIFIER_MODEL_NAME)
    records: list[dict[str, Any]] = []
    input_tokens = 0
    output_tokens = 0
    logical_calls = 0
    stop_reason = "COMPLETED"

    for scenario in scenarios:
        if logical_calls + 2 > args.max_logical_external_calls:
            stop_reason = "CALL_LIMIT_REACHED"
            break
        if (
            token_cost_usd(input_tokens, output_tokens)
            + RESERVE_USD_PER_SCENARIO
            > args.max_cost_usd
        ):
            stop_reason = "COST_LIMIT_REACHED"
            break
        element = _element(scenario)
        logger = PilotLogger()
        attempts_before = budget.attempts
        result = None
        error = ""
        started = time.perf_counter()
        try:
            result = answer_question(
                scenario["question"],
                embed_query=lambda _question: [1.0],
                vector_index=StaticIndex(
                    [SearchHit(element=element, score=1.0, rank=1)]
                ),
                generator=generator,
                classifier=classifier,
                event_logger=logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                top_k=1,
                generation_prompt_builder=build_deadline_calculation_prompt,
                generation_prompt_version=DEADLINE_CALCULATION_PROMPT_VERSION,
                classification_prompt_builder=build_deadline_classification_prompt,
                classification_prompt_version=DEADLINE_CLASSIFICATION_PROMPT_VERSION,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        generation_input = int(logger.generation.get("input_tokens", 0))
        generation_output = int(logger.generation.get("output_tokens", 0))
        classification_input = int(logger.classification.get("input_tokens", 0))
        classification_output = int(logger.classification.get("output_tokens", 0))
        scenario_input = generation_input + classification_input
        scenario_output = generation_output + classification_output
        input_tokens += scenario_input
        output_tokens += scenario_output
        logical_calls += budget.attempts - attempts_before
        generated = logger.generation.get("response_data") or {}
        answer = result.get("answer", "") if result else ""
        expects_date = scenario["group"] == "date"
        date_contract_ok = (
            len(generated.get("date_calculations", [])) == 1
            if expects_date
            else not generated.get("date_calculations", [])
        )
        record = {
            "scenario_id": scenario["id"],
            "group": scenario["group"],
            "question": scenario["question"],
            "expected_label": scenario["expected_label"],
            "predicted_label": result.get("answer_label") if result else None,
            "answer_status": result.get("answer_status") if result else None,
            "classification_ok": bool(result)
            and result.get("answer_label") == scenario["expected_label"],
            "content_ok": bool(result)
            and _content_ok(answer, scenario["required"]),
            "date_contract_ok": bool(result) and date_contract_ok,
            "composite_ok": bool(result)
            and result.get("answer_status") == "SUCCESS"
            and result.get("answer_label") == scenario["expected_label"]
            and _content_ok(answer, scenario["required"])
            and date_contract_ok,
            "answer": answer,
            "generation_response_data": generated,
            "input_tokens": scenario_input,
            "output_tokens": scenario_output,
            "estimated_cost_usd": token_cost_usd(
                scenario_input, scenario_output
            ),
            "elapsed_seconds": time.perf_counter() - started,
            "error": error or None,
        }
        records.append(record)
        with (args.output_dir / "records.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(
            f"{scenario['id']}: composite={record['composite_ok']} "
            f"error={error or 'none'}"
        )
        if error:
            stop_reason = "ERROR_FAIL_FAST"
            break

    date_records = [record for record in records if record["group"] == "date"]
    controls = [record for record in records if record["group"] == "control"]
    summary = {
        "scenario_count": len(scenarios),
        "completed_count": sum(record["error"] is None for record in records),
        "date_success": sum(record["composite_ok"] for record in date_records),
        "date_count": len(date_records),
        "control_success": sum(record["composite_ok"] for record in controls),
        "control_count": len(controls),
        "gate_passed": (
            stop_reason == "COMPLETED"
            and len(date_records) == 6
            and all(record["composite_ok"] for record in date_records)
            and len(controls) == 2
            and all(record["composite_ok"] for record in controls)
        ),
        "logical_external_calls": logical_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": args.max_cost_usd,
        "stop_reason": stop_reason,
        "sealed_holdout_accessed": False,
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if stop_reason == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
