"""Compare a required-facets generation prompt on fixed retrieved evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME
from eval.compare_embedding_models import load_elements
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_models import load_questions
from eval.evaluate_visual_answers import token_cost_usd
from src.contracts import SearchHit
from src.llm_provider import GeminiProvider
from src.query_service import (
    build_generation_prompt,
    answer_question,
    load_schema,
)


PROMPT_VERSION = "answer-claims-required-facets-v1"
DEFAULT_CASES = BASE_DIR / "eval/generation_facets_pilot_cases.json"
DEFAULT_QUESTIONS = BASE_DIR / "eval/evaluation_questions_500.csv"
DEFAULT_BASELINE = (
    BASE_DIR
    / "eval/results/retrieved_text_regression_e24d7d4_v2/evaluation/records.jsonl"
)
ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
RESERVE_USD_PER_CASE = 0.003


class FixedVectorIndex:
    def __init__(self, hits: list[SearchHit]):
        self.hits = hits

    def search(self, _query_vector: list[float], limit: int) -> list[SearchHit]:
        return self.hits[:limit]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def build_required_facets_prompt(
    question: str, hits: list[SearchHit], visual_assets: dict | None = None
) -> str:
    base = build_generation_prompt(question, hits, visual_assets)
    instruction = (
        "回答JSONを作る前に、次の確認を内部で行ってください。確認過程そのものは出力しません。\n"
        "1. 質問が明示的に求める必須項目を漏れなく列挙する。\n"
        "2. 各必須項目へ、取得根拠だけで完全に支持できるclaim、または具体的なmissing_conditionのどちらかを対応させる。\n"
        "3. 根拠同士が異なる取扱いを示し、適用関係を根拠だけで決められない場合は、一方を選ばず相違点と確認事項をmissing_conditionsへ入れる。\n"
        "4. 質問の必須項目に対応しない関連情報はclaimへ追加しない。\n"
        "5. 『場合があります』のように結果が確定しないときは、確定に必要な具体的条件をmissing_conditionsへ入れる。\n"
    )
    return instruction + base


def _joined_content(record: dict[str, Any]) -> str:
    claim_text = "\n".join(str(item.get("text", "")) for item in record["claims"])
    missing = "\n".join(record["missing_conditions"])
    return "\n".join((record.get("answer", ""), claim_text, missing))


def score_record(record: dict[str, Any], rule: dict[str, list[str]]) -> dict[str, Any]:
    content = _joined_content(record)
    required = {
        pattern: bool(re.search(pattern, content))
        for pattern in rule["required_patterns"]
    }
    forbidden = {
        pattern: bool(re.search(pattern, content))
        for pattern in rule["forbidden_patterns"]
    }
    return {
        "classification_ok": record.get("predicted_label") == record["expected_label"],
        "required_facets_ok": all(required.values()),
        "forbidden_claims_ok": not any(forbidden.values()),
        "required_pattern_results": required,
        "forbidden_pattern_results": forbidden,
        "overall_success": (
            not record.get("error")
            and record.get("predicted_label") == record["expected_label"]
            and all(required.values())
            and not any(forbidden.values())
        ),
    }


def _baseline_record(raw: dict[str, Any], question: dict[str, str]) -> dict[str, Any]:
    return {
        "question_id": raw["question_id"],
        "question": raw["question"],
        "expected_label": question["expected_answer_type"],
        "predicted_label": raw["predicted_label"],
        "answer": raw["answer"],
        "claims": raw["claims"],
        "missing_conditions": raw["missing_conditions"],
        "error": raw["error"],
    }


def _fixed_hits(raw: dict[str, Any], elements_by_id: dict[str, Any]) -> list[SearchHit]:
    hits = []
    for item in raw["retrieved"]:
        element = elements_by_id.get(item["element_id"])
        if element is None:
            raise ValueError(
                f"固定根拠が現在のcorpusにありません: {item['element_id']}"
            )
        hits.append(SearchHit(element=element, score=1.0, rank=int(item["rank"])))
    return hits


def _provider_error(error: str) -> bool:
    lowered = error.lower()
    return any(
        marker in lowered
        for marker in (
            "429",
            "resource_exhausted",
            "serviceunavailable",
            "deadlineexceeded",
            "connectionerror",
            "apierror",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    case_ids = [*cases["failure_ids"], *cases["control_ids"]]
    if set(case_ids) != set(cases["cases"]) or len(case_ids) != len(set(case_ids)):
        raise ValueError("pilot case IDの集合が一致しません")
    required_calls = len(case_ids) * 2
    if args.max_logical_external_calls < required_calls:
        raise ValueError(f"pilot完了には最大{required_calls} logical callsが必要です")
    if args.max_cost_usd <= 0:
        raise ValueError("費用上限は正数で指定してください")
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")

    questions = {
        row["question_id"]: row for row in load_questions(args.questions, "formal")
    }
    baseline_raw = {row["question_id"]: row for row in _load_jsonl(args.baseline)}
    missing = set(case_ids) - (set(questions) & set(baseline_raw))
    if missing:
        raise ValueError(f"質問またはbaselineがありません: {sorted(missing)}")
    baseline = {
        question_id: _baseline_record(baseline_raw[question_id], questions[question_id])
        for question_id in case_ids
    }
    baseline_scores = {
        question_id: score_record(record, cases["cases"][question_id])
        for question_id, record in baseline.items()
    }
    if any(baseline_scores[item]["overall_success"] for item in cases["failure_ids"]):
        raise ValueError("failure対象にbaseline成功例が含まれています")
    if not all(
        baseline_scores[item]["overall_success"] for item in cases["control_ids"]
    ):
        raise ValueError("control対象にbaseline失敗例が含まれています")

    args.output_dir.mkdir(parents=True)
    manifest = {
        "artifact_version": "generation-facets-prompt-comparison-v1",
        "prompt_version": PROMPT_VERSION,
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "failure_ids": cases["failure_ids"],
        "control_ids": cases["control_ids"],
        "max_logical_external_calls": args.max_logical_external_calls,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "fixed_retrieval": True,
        "sealed_holdout_accessed": False,
        "source_sha256": {
            "cases": _sha256(args.cases),
            "questions": _sha256(args.questions),
            "baseline": _sha256(args.baseline),
        },
    }
    _write_json(args.output_dir / "run_manifest.json", manifest)

    elements_by_id = {str(item.id): item for item in load_elements(BASE_DIR / "docs")}
    generator = GeminiProvider(LLM_MODEL_NAME)
    classifier = GeminiProvider(CLASSIFIER_MODEL_NAME)
    records_path = args.output_dir / "candidate_records.jsonl"
    candidate: dict[str, dict[str, Any]] = {}
    input_tokens = 0
    output_tokens = 0
    logical_calls = 0
    stop_reason = "COMPLETED"

    for question_id in case_ids:
        current_cost = token_cost_usd(input_tokens, output_tokens)
        if current_cost + RESERVE_USD_PER_CASE > args.max_cost_usd:
            stop_reason = "COST_LIMIT_REACHED"
            break
        if logical_calls + 2 > args.max_logical_external_calls:
            stop_reason = "CALL_LIMIT_REACHED"
            break
        raw = baseline_raw[question_id]
        row = questions[question_id]
        hits = _fixed_hits(raw, elements_by_id)
        logger = EvaluationLogger()
        started = time.perf_counter()
        try:
            result = answer_question(
                row["question"],
                embed_query=lambda _question: [0.0],
                vector_index=FixedVectorIndex(hits),
                generator=generator,
                classifier=classifier,
                event_logger=logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                top_k=len(hits),
                generation_prompt_builder=build_required_facets_prompt,
                generation_prompt_version=PROMPT_VERSION,
            )
            error = None
        except Exception as exc:
            result = None
            error = f"{type(exc).__name__}: {exc}"
        logical_calls += 2
        scenario_input = int(logger.generation.get("input_tokens", 0)) + int(
            logger.classification.get("input_tokens", 0)
        )
        scenario_output = int(logger.generation.get("output_tokens", 0)) + int(
            logger.classification.get("output_tokens", 0)
        )
        input_tokens += scenario_input
        output_tokens += scenario_output
        generated = logger.generation.get("response_data") or {}
        record = {
            "question_id": question_id,
            "role": "failure" if question_id in cases["failure_ids"] else "control",
            "question": row["question"],
            "expected_label": row["expected_answer_type"],
            "predicted_label": (
                result.get("answer_label")
                if result
                else logger.classification.get("derived_label")
            ),
            "answer": result.get("answer", "") if result else "",
            "claims": result.get("claims", [])
            if result
            else generated.get("claims", []),
            "missing_conditions": generated.get("missing_conditions", []),
            "input_tokens": scenario_input,
            "output_tokens": scenario_output,
            "cost_usd": token_cost_usd(scenario_input, scenario_output),
            "elapsed_seconds": time.perf_counter() - started,
            "error": error,
        }
        candidate[question_id] = record
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        print(
            f"{question_id}: label={record['predicted_label']}, error={error or 'none'}"
        )
        if error and _provider_error(error):
            stop_reason = "PROVIDER_ERROR_FAIL_FAST"
            break

    candidate_scores = {
        question_id: score_record(record, cases["cases"][question_id])
        for question_id, record in candidate.items()
    }
    improved = [
        item
        for item in cases["failure_ids"]
        if item in candidate_scores and candidate_scores[item]["overall_success"]
    ]
    regressed = [
        item
        for item in cases["control_ids"]
        if item in candidate_scores and not candidate_scores[item]["overall_success"]
    ]
    complete = len(candidate) == len(case_ids) and not any(
        record["error"] for record in candidate.values()
    )
    gate_passed = complete and len(improved) >= 2 and not regressed
    analysis = {
        "baseline_scores": baseline_scores,
        "candidate_scores": candidate_scores,
        "summary": {
            "completed_count": len(candidate),
            "expected_count": len(case_ids),
            "improved_failure_ids": improved,
            "improved_failure_count": len(improved),
            "regressed_control_ids": regressed,
            "regressed_control_count": len(regressed),
            "gate_passed": gate_passed,
            "decision": "ADOPT_FOR_FULL_REGRESSION" if gate_passed else "DO_NOT_ADOPT",
            "stop_reason": stop_reason,
            "logical_external_calls": logical_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        },
    }
    _write_json(args.output_dir / "analysis.json", analysis)
    print(json.dumps(analysis["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
