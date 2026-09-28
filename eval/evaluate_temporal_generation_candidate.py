"""Evaluate query decomposition plus deterministic pre-generation version guidance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME, TOP_K
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.compare_embedding_models import load_or_create_vectors
from eval.embedding_profiles import PROFILES
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_models import load_questions
from eval.evaluate_query_decomposition_answers import (
    QuestionAwareIndex,
    _provider,
    _provider_error,
    _scenario_logical_calls,
)
from eval.evaluate_retrieved_text_regression import prepare_text_corpus
from eval.evaluate_visual_answers import token_cost_usd
from eval.query_decomposition import decompose_query
from src.query_service import answer_question, build_generation_prompt, load_schema
from src.temporal_evidence import temporal_prompt_instruction


ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
VERSION_SCHEMA = BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
DEFAULT_INPUT = BASE_DIR / "eval/evaluation_questions_500.csv"
DEFAULT_QUERY_CACHE = BASE_DIR / ".eval_cache/large_formal_query_vectors.json"
DEFAULT_SUBQUERY_CACHE = (
    BASE_DIR / ".eval_cache/query_decomposition_gemini_001_queries.json"
)
DEFAULT_DOCUMENT_CACHE = (
    BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
)
TARGET_ID = "Q291"
PILOT_CONTROL_IDS = ("Q421", "Q426", "Q431")
PILOT_IDS = (TARGET_ID, *PILOT_CONTROL_IDS)
ADDITIONAL_SCOPE_IDS = ("Q186", "Q191", "Q286")
SELECTED_IDS = (*PILOT_IDS, *ADDITIONAL_SCOPE_IDS)
MAX_LOGICAL_EXTERNAL_CALLS_PER_SCENARIO = 3
RESERVE_USD_PER_SCENARIO = 0.005
CONTENT_RULES = {
    "Q186": {
        "required": (r"15[,.]?000円", r"超え"),
        "rejected": (r"16[,.]?000円",),
    },
    "Q191": {
        "required": (
            r"15[,.]?000円",
            r"(対象(ではありません|外)|満たしません|満たさない)",
        ),
        "rejected": (r"16[,.]?000円",),
    },
    "Q286": {
        "required": (r"(認定された月|認定月)",),
        "rejected": (r"翌月",),
    },
    "Q291": {
        "required": (r"(認定された月|認定月)", r"15日以内"),
        "rejected": (r"翌月",),
    },
    "Q421": {
        "required": (r"2\s*km", r"1[.]5\s*km"),
        "rejected": (),
    },
    "Q426": {
        "required": (r"16[,.]?000円", r"15[,.]?000円"),
        "rejected": (),
    },
    "Q431": {
        "required": (r"翌月", r"(認定された月|認定月)"),
        "rejected": (),
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _content_ok(question_id: str, answer: str) -> bool:
    rule = CONTENT_RULES[question_id]
    return all(re.search(pattern, answer) for pattern in rule["required"]) and not any(
        re.search(pattern, answer) for pattern in rule["rejected"]
    )


def _version_resolution_error(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    resolver = result.get("version_resolution", {})
    if resolver.get("status") != "RESOLUTION_FAILED":
        return ""
    detail = resolver.get("error_summary") or "structured result unavailable"
    return f"VersionResolverError: {detail}"


def _selected_ids(question_id: str | None) -> tuple[str, ...]:
    if question_id is None:
        return SELECTED_IDS
    if question_id not in SELECTED_IDS:
        raise ValueError(f"影響範囲外のquestion_idです: {question_id}")
    return (question_id,)


def _attempt_diagnostics(logger: EvaluationLogger) -> dict[str, Any]:
    return {
        "generation_status": logger.generation.get("status"),
        "generation_response_data": logger.generation.get("response_data"),
        "generation_error_summary": logger.generation.get("error_summary"),
        "classification_status": logger.classification.get("status"),
        "classification_error_summary": logger.classification.get("error_summary"),
    }


def build_temporal_generation_prompt(question: str, hits: list, visual_assets) -> str:
    instruction = temporal_prompt_instruction(question, hits)
    base = build_generation_prompt(question, hits, visual_assets)
    if instruction is None:
        raise ValueError("評価対象に生成前の版適用情報を作成できません")
    return f"{instruction}\n{base}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--subquery-cache", type=Path, default=DEFAULT_SUBQUERY_CACHE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--reuse-dir", type=Path)
    parser.add_argument("--question-id", choices=SELECTED_IDS)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.question_id is not None and args.reuse_dir is not None:
        raise ValueError("単一質問診断では既存結果を再利用しません")
    selected_ids = _selected_ids(args.question_id)
    all_questions = load_questions(args.input, "formal")
    by_id = {row["question_id"]: row for row in all_questions}
    questions = [by_id[question_id] for question_id in selected_ids]
    original_vectors = load_baseline_query_vectors(args.query_cache, all_questions)
    subqueries = list(
        dict.fromkeys(
            subquery
            for row in all_questions
            for subquery in decompose_query(row["question"])
            if decompose_query(row["question"]) != [row["question"]]
        )
    )
    profile = PROFILES["gemini-embedding-001"]
    subquery_ids = [
        f"query:{hashlib.sha256(query.encode()).hexdigest()}" for query in subqueries
    ]

    def cache_miss(_texts: list[str]) -> list[list[float]]:
        raise ValueError("subquery cacheがありません。APIで暗黙生成しません")

    subquery_vectors, cache_hit, _ = load_or_create_vectors(
        args.subquery_cache,
        profile=profile,
        kind="query-decomposition-v1",
        ids=subquery_ids,
        texts=subqueries,
        embed=cache_miss,
    )
    if not cache_hit:
        raise AssertionError("subquery cacheを再利用できませんでした")
    vectors = {
        **original_vectors,
        **dict(zip(subqueries, subquery_vectors, strict=True)),
    }
    index = QuestionAwareIndex(
        prepare_text_corpus(args.document_cache), vectors, decompose=True
    )

    expected_hashes = {
        "dataset_sha256": _sha256(args.input),
        "query_cache_sha256": _sha256(args.query_cache),
        "subquery_cache_sha256": _sha256(args.subquery_cache),
        "document_cache_sha256": _sha256(args.document_cache),
    }
    reused_by_id: dict[str, dict[str, Any]] = {}
    reuse_manifest = None
    if args.reuse_dir is not None:
        reuse_manifest_path = args.reuse_dir / "run_manifest.json"
        reuse_records_path = args.reuse_dir / "records.jsonl"
        reuse_manifest = json.loads(reuse_manifest_path.read_text(encoding="utf-8"))
        for key, value in expected_hashes.items():
            if reuse_manifest.get(key) != value:
                raise ValueError(f"再利用artifactの{key}が一致しません")
        if (
            reuse_manifest.get("generator_model") != LLM_MODEL_NAME
            or reuse_manifest.get("classifier_model") != CLASSIFIER_MODEL_NAME
            or reuse_manifest.get("top_k") != TOP_K
            or reuse_manifest.get("generation_candidate")
            != "deterministic temporal guidance prepended to current prompt"
        ):
            raise ValueError("再利用artifactの実行条件が一致しません")
        source_rules = reuse_manifest.get("content_rules", {})
        for record in _read_jsonl(reuse_records_path):
            question_id = record.get("question_id")
            if question_id not in PILOT_IDS:
                continue
            if record.get("error") or not record.get("composite_ok"):
                raise ValueError(f"再利用できないpilot結果です: {question_id}")
            if source_rules.get(question_id) != {
                key: list(value) for key, value in CONTENT_RULES[question_id].items()
            }:
                raise ValueError(
                    f"再利用artifactの内容基準が一致しません: {question_id}"
                )
            reused_by_id[question_id] = {**record, "reused": True}
        if set(reused_by_id) != set(PILOT_IDS):
            raise ValueError("pilot 4件をすべて再利用できません")

    pending_questions = [
        row for row in questions if row["question_id"] not in reused_by_id
    ]
    if args.max_cost_usd < len(pending_questions) * RESERVE_USD_PER_SCENARIO:
        raise ValueError("費用上限が未評価シナリオの予約額を下回っています")
    max_logical_external_calls = (
        len(pending_questions) * MAX_LOGICAL_EXTERNAL_CALLS_PER_SCENARIO
    )

    args.output_dir.mkdir(parents=True)
    records_path = args.output_dir / "records.jsonl"
    manifest = {
        "experiment": (
            "pre-generation-temporal-guidance-diagnostic-v1"
            if args.question_id is not None
            else "pre-generation-temporal-guidance-scope-v2"
        ),
        **expected_hashes,
        "target_id": TARGET_ID,
        "pilot_control_ids": list(PILOT_CONTROL_IDS),
        "additional_scope_ids": list(ADDITIONAL_SCOPE_IDS),
        "selected_ids": list(selected_ids),
        "content_rules": CONTENT_RULES,
        "retrieval": "query decomposition when a deterministic rule matches; otherwise dense",
        "generation_candidate": "deterministic temporal guidance prepended to current prompt",
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "top_k": TOP_K,
        "max_logical_external_calls": max_logical_external_calls,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "sealed_holdout_accessed": False,
        "production_integrated": False,
        "reuse": (
            {
                "source_dir": str(args.reuse_dir),
                "source_manifest_sha256": _sha256(args.reuse_dir / "run_manifest.json"),
                "source_records_sha256": _sha256(args.reuse_dir / "records.jsonl"),
                "reused_ids": sorted(reused_by_id),
            }
            if args.reuse_dir is not None
            else None
        ),
    }
    _write_json(args.output_dir / "run_manifest.json", manifest)

    generator = _provider(LLM_MODEL_NAME)
    classifier = _provider(CLASSIFIER_MODEL_NAME)
    resolver = _provider(CLASSIFIER_MODEL_NAME)
    input_tokens = 0
    output_tokens = 0
    logical_calls = 0
    records = [
        reused_by_id[question_id]
        for question_id in PILOT_IDS
        if question_id in reused_by_id
    ]
    if records:
        with records_path.open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    stop_reason = "COMPLETED"

    for row in pending_questions:
        if (
            token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_SCENARIO
            > args.max_cost_usd
        ):
            stop_reason = "COST_LIMIT_REACHED"
            break
        index.select_question(row["question"])
        logger = EvaluationLogger()
        result = None
        error = ""
        started = time.perf_counter()
        try:
            result = answer_question(
                row["question"],
                embed_query=lambda question: original_vectors[question],
                vector_index=index,
                generator=generator,
                classifier=classifier,
                version_resolver=resolver,
                event_logger=logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                version_resolution_schema=load_schema(VERSION_SCHEMA),
                top_k=TOP_K,
                generation_prompt_builder=build_temporal_generation_prompt,
                generation_prompt_version="answer-claims-v1+temporal-guidance-v1",
            )
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"

        error = error or _version_resolution_error(result)

        resolver_data = result.get("version_resolution", {}) if result else {}
        generation_input = int(logger.generation.get("input_tokens", 0))
        generation_output = int(logger.generation.get("output_tokens", 0))
        classification_input = int(logger.classification.get("input_tokens", 0))
        classification_output = int(logger.classification.get("output_tokens", 0))
        resolver_input = int(resolver_data.get("input_tokens", 0))
        resolver_output = int(resolver_data.get("output_tokens", 0))
        scenario_input = generation_input + classification_input + resolver_input
        scenario_output = generation_output + classification_output + resolver_output
        input_tokens += scenario_input
        output_tokens += scenario_output
        logical_calls += _scenario_logical_calls(logger, result)

        answer = result.get("answer", "") if result else ""
        classification_ok = bool(result) and (
            result.get("answer_label") == row["expected_answer_type"]
        )
        content_ok = bool(result) and _content_ok(row["question_id"], answer)
        support_ok = bool(result) and (
            not result.get("claims")
            or bool(
                (logger.classification.get("factors") or {}).get(
                    "answer_fully_supported"
                )
            )
        )
        references = result.get("references", []) if result else []
        record = {
            "question_id": row["question_id"],
            "role": (
                "target"
                if row["question_id"] == TARGET_ID
                else "additional_scope"
                if row["question_id"] in ADDITIONAL_SCOPE_IDS
                else "control"
            ),
            "reused": False,
            "question": row["question"],
            "temporal_instruction": temporal_prompt_instruction(
                row["question"], logger.retrieval_hits
            ),
            "answer": answer,
            "predicted_label": result.get("answer_label") if result else None,
            "classification_ok": classification_ok,
            "content_ok": content_ok,
            "support_ok": support_ok,
            "composite_ok": classification_ok and content_ok and support_ok,
            "retrieved": [
                {
                    "rank": rank,
                    "document_id": item.get("document_id"),
                    "heading": item.get("heading"),
                }
                for rank, item in enumerate(references, start=1)
            ],
            "input_tokens": scenario_input,
            "output_tokens": scenario_output,
            "estimated_cost_usd": token_cost_usd(scenario_input, scenario_output),
            "version_resolution": resolver_data,
            **_attempt_diagnostics(logger),
            "elapsed_seconds": time.perf_counter() - started,
            "error": error or None,
        }
        records.append(record)
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(
            f"{row['question_id']}: label={classification_ok} "
            f"content={content_ok} support={support_ok} error={error or 'none'}"
        )
        if error and _provider_error(error):
            stop_reason = "PROVIDER_ERROR_FAIL_FAST"
            break

    if logical_calls > max_logical_external_calls:
        raise RuntimeError("logical external call上限を超えました")
    completed = [row for row in records if not row["error"]]
    summary = {
        "scope_scenario_count": len(selected_ids),
        "completed_count": len(completed),
        "reused_count": len(reused_by_id),
        "new_scenario_count": len(pending_questions),
        "new_logical_external_calls": logical_calls,
        "new_input_tokens": input_tokens,
        "new_output_tokens": output_tokens,
        "new_estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "new_max_cost_usd": args.max_cost_usd,
        "historical_reused_estimated_cost_usd": sum(
            float(row.get("estimated_cost_usd", 0)) for row in reused_by_id.values()
        ),
        "target_composite_ok": any(
            row["question_id"] == TARGET_ID and row["composite_ok"] for row in completed
        ),
        "additional_scope_composite_correct": sum(
            row["composite_ok"]
            for row in completed
            if row["question_id"] in ADDITIONAL_SCOPE_IDS
        ),
        "additional_scope_count": sum(
            question_id in ADDITIONAL_SCOPE_IDS for question_id in selected_ids
        ),
        "scope_composite_correct": sum(row["composite_ok"] for row in completed),
        "gate_passed": (
            stop_reason == "COMPLETED"
            and len(completed) == len(selected_ids)
            and all(row["composite_ok"] for row in completed)
        ),
        "stop_reason": stop_reason,
        "sealed_holdout_accessed": False,
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
