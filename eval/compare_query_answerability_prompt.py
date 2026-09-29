"""Compare a narrow answerability-alignment prompt on fixed trigger cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME
from eval.compare_query_trigger_retrieval import _required_groups, _retrieval_ok
from eval.embedding_profiles import PROFILES
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_query_decomposition_answers import (
    QuestionAwareIndex,
    _provider,
    _provider_error,
    _scenario_logical_calls,
)
from eval.evaluate_query_trigger_answers import (
    CONTENT_RULES,
    MIN_SAFE_SCENARIO_INTERVAL_SECONDS,
    _pacing_delay,
)
from eval.evaluate_retrieved_text_regression import prepare_text_corpus
from eval.evaluate_visual_answers import token_cost_usd
from eval.query_decomposition_cache import load_cached_subquery_vectors
from src.query_decomposition import decompose_query
from src.query_service import answer_question, load_schema
from src.temporal_evidence import build_temporal_generation_prompt


INPUT = BASE_DIR / "eval/query_trigger_robustness_cases.json"
BASELINE = BASE_DIR / "eval/results/query_trigger_answer_comparison_v2/records.jsonl"
QUERY_CACHE = BASE_DIR / ".eval_cache/query_trigger_robustness_queries.json"
DOCUMENT_CACHE = BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
VERSION_SCHEMA = BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
FAILURE_IDS = ("G02", "G03", "G05", "G06", "G07", "G08")
CONTROL_IDS = ("G01", "G04", "G09")
CASE_IDS = (*FAILURE_IDS, *CONTROL_IDS)
MAX_LOGICAL_EXTERNAL_CALLS = len(CASE_IDS) * 3
PROMPT_VERSION = "answer-claims-v1+answerability-alignment-v1+temporal-guidance-v1"


def build_answerability_alignment_prompt(question, hits, visual_assets=None) -> str:
    instruction = (
        "missing_conditionsには、質問へ答えるために必須で、取得根拠から答えられない事項だけを入れてください。\n"
        "- 根拠が『通勤実態がなくなった場合』のような出来事条件を示す場合、質問の『いつ』『時期』はその出来事条件で回答できます。\n"
        "- 質問が具体的な日付、月、何日以内という粒度を明示した場合だけ、それより粗い出来事条件を不足と扱います。\n"
        "- 複数文書の根拠付きclaimが質問の各項目を満たす場合、文書間を結ぶ一文がないこと自体は不足ではありません。\n"
        "- claimで回答した項目をmissing_conditionsへ重複して入れないでください。\n"
    )
    return instruction + build_temporal_generation_prompt(question, hits, visual_assets)


def _load_baseline() -> dict[str, dict]:
    rows = [json.loads(line) for line in BASELINE.read_text(encoding="utf-8").splitlines()]
    selected = {row["id"]: row for row in rows if row["variant"] == "candidate" and row["id"] in CASE_IDS}
    if set(selected) != set(CASE_IDS):
        raise ValueError("固定baselineに必要なcaseがありません")
    if any(selected[item]["composite_ok"] for item in FAILURE_IDS):
        raise ValueError("failure対象にbaseline成功があります")
    if not all(selected[item]["composite_ok"] for item in CONTROL_IDS):
        raise ValueError("control対象にbaseline失敗があります")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument("--min-scenario-interval-seconds", type=float, default=15.0)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_logical_external_calls < MAX_LOGICAL_EXTERNAL_CALLS or args.max_logical_external_calls > 30:
        raise ValueError(f"logical call上限は{MAX_LOGICAL_EXTERNAL_CALLS}以上30以下にしてください")
    if args.max_cost_usd < 0.045 or args.max_cost_usd > 0.05:
        raise ValueError("費用上限はUS$0.045以上US$0.05以下にしてください")
    if args.min_scenario_interval_seconds < MIN_SAFE_SCENARIO_INTERVAL_SECONDS:
        raise ValueError("シナリオ開始間隔は15秒以上にしてください")

    baseline = _load_baseline()
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    cases = [case for case in payload["cases"] if case["id"] in CASE_IDS]
    all_positive = [case["question"] for case in payload["cases"] if case["family"] in {"move_positive", "birth_positive"}]
    texts = all_positive + list(dict.fromkeys(query for text in all_positive for query in decompose_query(text) if query != text))
    profile = PROFILES["gemini-embedding-001"]
    ids = [f"query:{hashlib.sha256(text.encode()).hexdigest()}" for text in texts]
    vectors = load_cached_subquery_vectors(QUERY_CACHE, profile=profile, kind="query-trigger-robustness-v1", ids=ids)
    vectors_by_text = dict(zip(texts, vectors, strict=True))
    index = QuestionAwareIndex(prepare_text_corpus(DOCUMENT_CACHE), vectors_by_text, decompose=True)

    args.output_dir.mkdir(parents=True)
    manifest = {
        "experiment": "query-answerability-prompt-comparison-v1",
        "prompt_version": PROMPT_VERSION,
        "failure_ids": list(FAILURE_IDS),
        "control_ids": list(CONTROL_IDS),
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "fixed_retrieval": True,
        "max_logical_external_calls": args.max_logical_external_calls,
        "max_cost_usd": args.max_cost_usd,
        "min_scenario_interval_seconds": args.min_scenario_interval_seconds,
        "retry_count": 0,
        "sealed_holdout_accessed": False,
    }
    (args.output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    generator = _provider(LLM_MODEL_NAME)
    classifier = _provider(CLASSIFIER_MODEL_NAME)
    resolver = _provider(CLASSIFIER_MODEL_NAME)
    records = []
    logical_calls = input_tokens = output_tokens = 0
    stop_reason = "COMPLETED"
    last_started = None
    for case in cases:
        if token_cost_usd(input_tokens, output_tokens) + 0.005 > args.max_cost_usd:
            stop_reason = "COST_LIMIT_REACHED"
            break
        delay = _pacing_delay(last_started, time.monotonic(), args.min_scenario_interval_seconds)
        if delay:
            time.sleep(delay)
        last_started = time.monotonic()
        index.select_question(case["question"])
        logger = EvaluationLogger()
        result = None
        error = ""
        started = time.perf_counter()
        try:
            result = answer_question(
                case["question"], embed_query=lambda query: vectors_by_text[query],
                vector_index=index, generator=generator, classifier=classifier,
                version_resolver=resolver, event_logger=logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                version_resolution_schema=load_schema(VERSION_SCHEMA), top_k=8,
                generation_prompt_builder=build_answerability_alignment_prompt,
                generation_prompt_version=PROMPT_VERSION,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        generated = logger.generation.get("response_data") or {}
        answer = result.get("answer", "") if result else ""
        retrieval_ok = _retrieval_ok(logger.retrieval_hits, _required_groups(case["family"]))
        content_ok = bool(result) and all(re.search(pattern, answer) for pattern in CONTENT_RULES[case["id"]])
        classification_ok = bool(result) and result.get("answer_label") == "根拠十分"
        support_ok = bool(result) and bool((logger.classification.get("factors") or {}).get("answer_fully_supported"))
        version_resolution = result.get("version_resolution", {}) if result else {}
        scenario_in = int(logger.generation.get("input_tokens", 0)) + int(logger.classification.get("input_tokens", 0)) + int(version_resolution.get("input_tokens", 0))
        scenario_out = int(logger.generation.get("output_tokens", 0)) + int(logger.classification.get("output_tokens", 0)) + int(version_resolution.get("output_tokens", 0))
        input_tokens += scenario_in
        output_tokens += scenario_out
        logical_calls += _scenario_logical_calls(logger, result)
        record = {
            "id": case["id"], "role": "failure" if case["id"] in FAILURE_IDS else "control",
            "question": case["question"], "retrieval_ok": retrieval_ok,
            "answer": answer, "claims": generated.get("claims", []),
            "missing_conditions": generated.get("missing_conditions", []),
            "classification_factors": logger.classification.get("factors"),
            "content_ok": content_ok, "classification_ok": classification_ok,
            "support_ok": support_ok,
            "composite_ok": retrieval_ok and content_ok and classification_ok and support_ok,
            "estimated_cost_usd": token_cost_usd(scenario_in, scenario_out),
            "elapsed_seconds": time.perf_counter() - started, "error": error or None,
        }
        records.append(record)
        with (args.output_dir / "records.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        if error and _provider_error(error):
            stop_reason = "PROVIDER_ERROR_FAIL_FAST"
            break
    candidate = {row["id"]: row for row in records}
    common = set(candidate) & set(baseline)
    improvements = sorted(item for item in common if not baseline[item]["composite_ok"] and candidate[item]["composite_ok"])
    regressions = sorted(item for item in common if baseline[item]["composite_ok"] and not candidate[item]["composite_ok"])
    summary = {
        "completed_cases": len(records), "baseline_success": sum(baseline[item]["composite_ok"] for item in CASE_IDS),
        "candidate_success": sum(row["composite_ok"] for row in records),
        "improved_ids": improvements, "regressed_ids": regressions,
        "gate_passed": stop_reason == "COMPLETED" and len(records) == len(CASE_IDS) and len(improvements) >= 2 and not regressions,
        "logical_external_calls": logical_calls, "max_logical_external_calls": args.max_logical_external_calls,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens), "max_cost_usd": args.max_cost_usd,
        "stop_reason": stop_reason, "sealed_holdout_accessed": False,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
