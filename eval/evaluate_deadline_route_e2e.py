"""Bounded end-to-end pilot for newly supported deadline-route expressions."""

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
    should_use_deadline_calculation,
)


ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
MAX_LOGICAL_EXTERNAL_CALLS = 12
MAX_COST_USD = 0.01
RESERVE_USD_PER_SCENARIO = 0.0015
ROUTE_VARIANTS = (
    {
        "id": "DRE2E-01",
        "source_id": "ACV2-D01",
        "question": "2027-10-10に受験しました。提出期限日はいつですか。",
        "required": (r"2027年10月30日正午",),
    },
    {
        "id": "DRE2E-02",
        "source_id": "ACV2-D02",
        "question": "2028/2/28に届出しました。補足資料の締め切り日はいつですか。",
        "required": (r"2028年2月29日17時00分",),
    },
    {
        "id": "DRE2E-03",
        "source_id": "ACV2-D03",
        "question": "2027-12-31から数えた登録の期限日はいつですか。",
        "required": (r"2028年1月1日",),
    },
    {
        "id": "DRE2E-04",
        "source_id": "ACV2-D04",
        "question": "受理日が2027年5月15日です。処理の期限となる日はいつですか。",
        "required": (r"2027年5月24日",),
    },
)


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
    if not 8 <= args.max_logical_external_calls <= MAX_LOGICAL_EXTERNAL_CALLS:
        raise ValueError("logical external call上限は8以上12以下です")
    if not len(ROUTE_VARIANTS) * RESERVE_USD_PER_SCENARIO <= args.max_cost_usd <= MAX_COST_USD:
        raise ValueError("費用上限はUS$0.006以上US$0.01以下です")
    if not all(should_use_deadline_calculation(row["question"]) for row in ROUTE_VARIANTS):
        raise ValueError("route対象外の評価質問が含まれています")

    source_by_id = {row["id"]: row for row in SCENARIOS}
    args.output_dir.mkdir(parents=True)
    _write_json(
        args.output_dir / "run_manifest.json",
        {
            "experiment": "deadline-route-e2e-v1",
            "scenario_ids": [row["id"] for row in ROUTE_VARIANTS],
            "generator_model": LLM_MODEL_NAME,
            "classifier_model": CLASSIFIER_MODEL_NAME,
            "generation_prompt_version": DEADLINE_CALCULATION_PROMPT_VERSION,
            "classification_prompt_version": DEADLINE_CLASSIFICATION_PROMPT_VERSION,
            "max_logical_external_calls": args.max_logical_external_calls,
            "max_cost_usd": args.max_cost_usd,
            "provider_retry_policy": {
                "max_retries": 2,
                "retryable_status_codes": [503],
                "minimum_call_interval_seconds": 5.1,
                "backoff_seconds": [5.1, 10.2],
                "jitter_max_seconds": 1.0,
            },
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
    stop_reason = "COMPLETED"

    for variant in ROUTE_VARIANTS:
        if budget.attempts + 2 > args.max_logical_external_calls:
            stop_reason = "CALL_LIMIT_REACHED"
            break
        if token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_SCENARIO > args.max_cost_usd:
            stop_reason = "COST_LIMIT_REACHED"
            break
        source = dict(source_by_id[variant["source_id"]])
        source["id"] = variant["id"]
        source["question"] = variant["question"]
        element = _element(source)
        logger = PilotLogger()
        attempts_before = budget.attempts
        started = time.perf_counter()
        result = None
        error = ""
        try:
            result = answer_question(
                source["question"],
                embed_query=lambda _question: [1.0],
                vector_index=StaticIndex([SearchHit(element=element, score=1.0, rank=1)]),
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

        scenario_input = int(logger.generation.get("input_tokens", 0)) + int(
            logger.classification.get("input_tokens", 0)
        )
        scenario_output = int(logger.generation.get("output_tokens", 0)) + int(
            logger.classification.get("output_tokens", 0)
        )
        input_tokens += scenario_input
        output_tokens += scenario_output
        answer = result.get("answer", "") if result else ""
        generated = logger.generation.get("response_data") or {}
        record = {
            "scenario_id": variant["id"],
            "source_id": variant["source_id"],
            "question": source["question"],
            "route_selected": should_use_deadline_calculation(source["question"]),
            "predicted_label": result.get("answer_label") if result else None,
            "answer_status": result.get("answer_status") if result else None,
            "content_ok": bool(result) and _content_ok(answer, variant["required"]),
            "date_contract_ok": bool(result) and len(generated.get("date_calculations", [])) == 1,
            "composite_ok": bool(result)
            and result.get("answer_status") == "SUCCESS"
            and result.get("answer_label") == "根拠十分"
            and _content_ok(answer, variant["required"])
            and len(generated.get("date_calculations", [])) == 1,
            "answer": answer,
            "generation_response_data": generated,
            "logical_external_calls": budget.attempts - attempts_before,
            "input_tokens": scenario_input,
            "output_tokens": scenario_output,
            "estimated_cost_usd": token_cost_usd(scenario_input, scenario_output),
            "elapsed_seconds": time.perf_counter() - started,
            "error": error or None,
        }
        records.append(record)
        with (args.output_dir / "records.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{variant['id']}: composite={record['composite_ok']} error={error or 'none'}")
        if error:
            stop_reason = "ERROR_FAIL_FAST"
            break

    summary = {
        "scenario_count": len(ROUTE_VARIANTS),
        "completed_count": len(records),
        "composite_success": sum(record["composite_ok"] for record in records),
        "gate_passed": stop_reason == "COMPLETED"
        and len(records) == len(ROUTE_VARIANTS)
        and all(record["composite_ok"] for record in records),
        "logical_external_calls": budget.attempts,
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
