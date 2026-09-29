"""Compare end-to-end answers for fixed query-trigger paraphrases."""

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
from eval.evaluate_retrieved_text_regression import prepare_text_corpus
from eval.evaluate_visual_answers import token_cost_usd
from eval.query_decomposition_cache import load_cached_subquery_vectors
from src.query_decomposition import decompose_query
from src.query_service import answer_question, load_schema
from src.temporal_evidence import build_temporal_generation_prompt


INPUT = BASE_DIR / "eval/query_trigger_robustness_cases.json"
QUERY_CACHE = BASE_DIR / ".eval_cache/query_trigger_robustness_queries.json"
DOCUMENT_CACHE = BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
VERSION_SCHEMA = BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
TARGET_IDS = {f"G{index:02d}" for index in range(1, 9)} | {"G09"}
MAX_CALLS = len(TARGET_IDS) * 2 * 3
MIN_SAFE_SCENARIO_INTERVAL_SECONDS = 15.0
CONTENT_RULES = {
    **{
        f"G{index:02d}": (r"支給停止|停止", r"住所変更届|住所.*届")
        for index in range(1, 9)
    },
    "G09": (r"認定.*月|認定月", r"15日以内"),
}
CONTENT_RULES["G06"] += (r"14日以内",)
CONTENT_RULES["G07"] += (r"14日以内",)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pacing_delay(last_started: float | None, now: float, interval: float) -> float:
    if last_started is None:
        return 0.0
    return max(0.0, interval - (now - last_started))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument("--question-ids", nargs="+", choices=sorted(TARGET_IDS))
    parser.add_argument(
        "--min-scenario-interval-seconds",
        type=float,
        default=MIN_SAFE_SCENARIO_INTERVAL_SECONDS,
    )
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    selected_ids = set(args.question_ids or TARGET_IDS)
    minimum_cost_reserve = len(selected_ids) * 2 * 0.005
    if args.max_cost_usd < minimum_cost_reserve or args.max_cost_usd > 0.10:
        raise ValueError(
            f"費用上限はUS${minimum_cost_reserve:.2f}以上US$0.10以下にしてください"
        )
    if args.min_scenario_interval_seconds < MIN_SAFE_SCENARIO_INTERVAL_SECONDS:
        raise ValueError("シナリオ開始間隔は15秒以上にしてください")

    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    cases = [case for case in payload["cases"] if case["id"] in selected_ids]
    texts = [case["question"] for case in payload["cases"] if case["family"] in {"move_positive", "birth_positive"}]
    texts += list(dict.fromkeys(query for text in texts for query in decompose_query(text) if query != text))
    profile = PROFILES["gemini-embedding-001"]
    ids = [f"query:{hashlib.sha256(text.encode()).hexdigest()}" for text in texts]
    vectors = load_cached_subquery_vectors(QUERY_CACHE, profile=profile, kind="query-trigger-robustness-v1", ids=ids)
    vectors_by_text = dict(zip(texts, vectors, strict=True))
    base_index = prepare_text_corpus(DOCUMENT_CACHE)
    indexes = {
        "baseline": QuestionAwareIndex(base_index, vectors_by_text, decompose=False),
        "candidate": QuestionAwareIndex(base_index, vectors_by_text, decompose=True),
    }
    args.output_dir.mkdir(parents=True)
    manifest = {
        "experiment": "query-trigger-answer-comparison-v1",
        "dataset_sha256": _sha256(INPUT),
        "query_cache_sha256": _sha256(QUERY_CACHE),
        "document_cache_sha256": _sha256(DOCUMENT_CACHE),
        "target_ids": sorted(selected_ids),
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "top_k": 8,
        "max_logical_external_calls": MAX_CALLS,
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
    last_scenario_started = None
    for case in cases:
        for variant, index in indexes.items():
            if token_cost_usd(input_tokens, output_tokens) + 0.005 > args.max_cost_usd:
                stop_reason = "COST_LIMIT_REACHED"
                break
            delay = _pacing_delay(
                last_scenario_started,
                time.monotonic(),
                args.min_scenario_interval_seconds,
            )
            if delay:
                time.sleep(delay)
            last_scenario_started = time.monotonic()
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
                    generation_prompt_builder=build_temporal_generation_prompt,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            answer = result.get("answer", "") if result else ""
            retrieval_ok = _retrieval_ok(logger.retrieval_hits, _required_groups(case["family"]))
            content_ok = bool(result) and all(re.search(pattern, answer) for pattern in CONTENT_RULES[case["id"]])
            classification_ok = bool(result) and result.get("answer_label") == "根拠十分"
            support_ok = bool(result) and bool((logger.classification.get("factors") or {}).get("answer_fully_supported"))
            generation = logger.generation
            classification = logger.classification
            version_resolution = result.get("version_resolution", {}) if result else {}
            scenario_in = (
                int(generation.get("input_tokens", 0))
                + int(classification.get("input_tokens", 0))
                + int(version_resolution.get("input_tokens", 0))
            )
            scenario_out = (
                int(generation.get("output_tokens", 0))
                + int(classification.get("output_tokens", 0))
                + int(version_resolution.get("output_tokens", 0))
            )
            input_tokens += scenario_in
            output_tokens += scenario_out
            logical_calls += _scenario_logical_calls(logger, result)
            record = {
                "id": case["id"], "variant": variant, "question": case["question"],
                "retrieval_ok": retrieval_ok, "answer": answer,
                "content_ok": content_ok, "classification_ok": classification_ok,
                "support_ok": support_ok,
                "composite_ok": retrieval_ok and content_ok and classification_ok and support_ok,
                "generation_response_data": generation.get("response_data"),
                "classification_factors": classification.get("factors"),
                "classification_derived_label": classification.get("derived_label"),
                "version_resolution": version_resolution,
                "estimated_cost_usd": token_cost_usd(scenario_in, scenario_out),
                "elapsed_seconds": time.perf_counter() - started, "error": error or None,
            }
            records.append(record)
            with (args.output_dir / "records.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            if error and _provider_error(error):
                stop_reason = "PROVIDER_ERROR_FAIL_FAST"
                break
        if stop_reason != "COMPLETED":
            break
    by_variant = {name: sum(row["composite_ok"] for row in records if row["variant"] == name) for name in indexes}
    baseline_by_id = {row["id"]: row for row in records if row["variant"] == "baseline"}
    candidate_by_id = {row["id"]: row for row in records if row["variant"] == "candidate"}
    common = set(baseline_by_id) & set(candidate_by_id)
    regressions = sorted(item for item in common if baseline_by_id[item]["composite_ok"] and not candidate_by_id[item]["composite_ok"])
    improvements = sorted(item for item in common if not baseline_by_id[item]["composite_ok"] and candidate_by_id[item]["composite_ok"])
    summary = {
        "completed_scenarios": len(records), "success_by_variant": by_variant,
        "improved_ids": improvements, "regressed_ids": regressions,
        "gate_passed": stop_reason == "COMPLETED"
        and len(records) == len(selected_ids) * 2
        and by_variant["candidate"] > by_variant["baseline"]
        and not regressions,
        "logical_external_calls": logical_calls, "max_logical_external_calls": MAX_CALLS,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": args.max_cost_usd, "stop_reason": stop_reason,
        "sealed_holdout_accessed": False,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
