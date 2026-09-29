"""Evaluate answer-contract v2 on the 30-question visual development split."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME, TOP_K
from eval.evaluate_visual_answers import (
    DEFAULT_DATASET,
    DEFAULT_FIXTURE_MANIFEST,
    EvaluationEventLogger,
    _portable_path,
    _read_json,
    _sha256,
    _write_json,
    evaluate_visual_answers,
    prepare_visual_corpus,
)
from src.asset_store import LocalAssetReader
from src.embeddings import get_embeddings
from src.llm_provider import GeminiProvider
from src.query_decomposition import DecomposedVectorIndex
from src.query_service import (
    CLASSIFICATION_PROMPT_V2_VERSION,
    answer_question,
    build_classification_prompt_v2,
    load_schema,
)
from src.temporal_evidence import (
    ANSWER_CONTRACT_V2_PROMPT_VERSION,
    build_answer_contract_v2_prompt,
)


ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v2.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
VERSION_SCHEMA = BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
MAX_SCENARIOS = 30
MAX_LOGICAL_EXTERNAL_CALLS = 1 + MAX_SCENARIOS * 4
RESERVE_USD_PER_SCENARIO = 0.002


def _manifest(
    *,
    dataset_path: Path,
    fixture_manifest_path: Path,
    max_cost_usd: float,
    max_logical_external_calls: int,
) -> dict[str, Any]:
    return {
        "experiment": "answer-contract-v2-visual-regression-v1",
        "dataset_path": _portable_path(dataset_path),
        "dataset_sha256": _sha256(dataset_path),
        "fixture_manifest_path": _portable_path(fixture_manifest_path),
        "fixture_manifest_sha256": _sha256(fixture_manifest_path),
        "split": "development",
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "answer_schema": str(ANSWER_SCHEMA.relative_to(BASE_DIR)),
        "generation_prompt_version": ANSWER_CONTRACT_V2_PROMPT_VERSION,
        "classification_prompt_version": CLASSIFICATION_PROMPT_V2_VERSION,
        "query_decomposition": "query-decomposition-v1",
        "version_resolver": "version-resolution-v2",
        "embedding_model": "gemini-embedding-001",
        "top_k": TOP_K,
        "scenario_count": MAX_SCENARIOS,
        "max_logical_external_calls": max_logical_external_calls,
        "retry_count": 0,
        "max_cost_usd": max_cost_usd,
        "per_scenario_cost_reserve_usd": RESERVE_USD_PER_SCENARIO,
        "stop_conditions": ["provider or candidate error", "cost reserve"],
        "sealed_holdout_accessed": False,
        "production_deployed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fixture-manifest", type=Path, default=DEFAULT_FIXTURE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_logical_external_calls > MAX_LOGICAL_EXTERNAL_CALLS:
        raise ValueError("logical external call上限は121です")
    if args.max_cost_usd < MAX_SCENARIOS * RESERVE_USD_PER_SCENARIO:
        raise ValueError("費用上限が30問の安全予約額を下回っています")

    dataset = _read_json(args.dataset)
    if dataset.get("split") != "development" or len(dataset["scenarios"]) != 30:
        raise ValueError("development図表質問は30件必要です")
    args.output_dir.mkdir(parents=True)
    _write_json(
        args.output_dir / "run_manifest.json",
        _manifest(
            dataset_path=args.dataset,
            fixture_manifest_path=args.fixture_manifest,
            max_cost_usd=args.max_cost_usd,
            max_logical_external_calls=args.max_logical_external_calls,
        ),
    )

    embeddings = get_embeddings()
    with tempfile.TemporaryDirectory(prefix="answer-contract-v2-visual-") as asset_dir:
        corpus = prepare_visual_corpus(
            args.fixture_manifest, Path(asset_dir), embeddings
        )
        generator = GeminiProvider(LLM_MODEL_NAME)
        classifier = GeminiProvider(CLASSIFIER_MODEL_NAME)
        resolver = GeminiProvider(CLASSIFIER_MODEL_NAME)

        def generate(question: str) -> dict[str, Any]:
            event_logger = EvaluationEventLogger()
            index = DecomposedVectorIndex(
                question=question,
                base_index=corpus.index,
                embed_query=embeddings.embed_query,
            )
            result = answer_question(
                question,
                embed_query=embeddings.embed_query,
                vector_index=index,
                generator=generator,
                classifier=classifier,
                version_resolver=resolver,
                event_logger=event_logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                version_resolution_schema=load_schema(VERSION_SCHEMA),
                top_k=TOP_K,
                generation_prompt_builder=build_answer_contract_v2_prompt,
                generation_prompt_version=ANSWER_CONTRACT_V2_PROMPT_VERSION,
                classification_prompt_builder=build_classification_prompt_v2,
                classification_prompt_version=CLASSIFICATION_PROMPT_V2_VERSION,
                visual_asset_loader=lambda ids: [
                    corpus.assets[element_id]
                    for element_id in ids
                    if element_id in corpus.assets
                ],
                asset_reader=LocalAssetReader(),
                max_visual_assets=3,
            )
            classification_attempts = [
                attempt
                for attempt in event_logger.classification_attempts
                if str(attempt.get("prompt_version", "")).startswith(
                    "answer-classification"
                )
            ]
            result["_evaluation_classification_factors"] = (
                classification_attempts[-1].get("factors")
                if classification_attempts
                else None
            )
            generation_attempt = event_logger.generation_attempts[-1]
            result["_evaluation_generation_data"] = generation_attempt.get(
                "response_data", {}
            )
            return result

        summary = evaluate_visual_answers(
            dataset=dataset,
            output_dir=args.output_dir / "evaluation",
            generate_fn=generate,
            fixture_by_element=corpus.fixture_by_element,
            max_scenarios=MAX_SCENARIOS,
            max_cost_usd=args.max_cost_usd,
            per_scenario_cost_reserve_usd=RESERVE_USD_PER_SCENARIO,
        )
    summary["logical_external_call_upper_bound"] = MAX_LOGICAL_EXTERNAL_CALLS
    summary["sealed_holdout_accessed"] = False
    _write_json(args.output_dir / "evaluation" / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["stop_reason"] == "SCENARIO_LIMIT_REACHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
