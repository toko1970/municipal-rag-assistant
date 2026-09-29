"""Plan or run the bounded text sealed-holdout prediction pass.

The runner can read sealed source documents only in ``run`` mode. It never accepts
or reads a gold path, so predictions can be frozen before the answer key is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from qdrant_client import QdrantClient

from config import BASE_DIR, GOOGLE_API_KEY
from eval.evaluate_contextual_answer_candidate import EvaluationLogger
from eval.evaluate_query_decomposition_answers import (
    QuestionAwareIndex,
    _provider_error,
)
from eval.evaluate_visual_answers import token_cost_usd
from src.embedding_representation import contextual_heading_document_text
from src.embeddings import get_embeddings
from src.ingestion import build_markdown_elements
from src.llm_provider import GeminiProvider
from src.qdrant_index import QdrantVectorIndex
from src.query_decomposition import decompose_query
from src.query_service import answer_question, load_schema
from src.temporal_evidence import (
    TEMPORAL_GENERATION_PROMPT_VERSION,
    build_temporal_generation_prompt,
)


DEFAULT_MANIFEST = BASE_DIR / "eval/text_holdout/public_manifest.json"
DEFAULT_CONFIG = BASE_DIR / "eval/text_holdout/candidate_config.json"
DEFAULT_QUESTIONS = BASE_DIR / "eval/text_holdout/questions.json"
ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
VERSION_SCHEMA = BASE_DIR / "design/schemas/version-resolution-v1.schema.json"
RESERVE_USD_PER_EXPRESSION = 0.0015
EMBEDDING_COST_RESERVE_USD = 0.005


@dataclass
class HoldoutEvaluationLogger(EvaluationLogger):
    """Retain every classifier/resolver attempt for exact call accounting."""

    classification_attempts: list[dict[str, Any]] = field(default_factory=list)

    def record_classification_attempt(self, request_id, **kwargs):
        self.classification_attempts.append(kwargs)
        return super().record_classification_attempt(request_id, **kwargs)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR))
    except ValueError:
        return str(path.resolve())


def _provider(model: str) -> GeminiProvider:
    client = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
        max_retries=0,
    )
    return GeminiProvider(model, client=client)


def _expressions(questions: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "scenario_id": scenario["scenario_id"],
            "variant_type": expression["variant_type"],
            "question": expression["question"],
        }
        for scenario in questions["scenarios"]
        for expression in scenario["expressions"]
    ]


def build_plan(
    manifest: dict[str, Any],
    candidate: dict[str, Any],
    questions: dict[str, Any],
) -> dict[str, Any]:
    policy = candidate["execution_policy"]
    if manifest["state"] != "CANDIDATE_FROZEN":
        raise ValueError("prediction runにはCANDIDATE_FROZEN stateが必要です")
    if candidate["sealed_holdout_accessed"] is not False:
        raise ValueError("candidateはsealed holdout未参照で固定する必要があります")
    if policy["gold_available_to_runner"] is not False:
        raise ValueError("prediction runnerへgoldを渡すことは禁止です")
    if policy["retry_count"] != 0 or not policy["stop_on_provider_error"]:
        raise ValueError("retry 0 / provider error fail-fastが必要です")
    expressions = _expressions(questions)
    if len(expressions) != manifest["questions"]["expression_count"]:
        raise ValueError("公開質問の表現数がmanifestと一致しません")
    return {
        "holdout_id": manifest["holdout_id"],
        "candidate_git_commit": manifest["candidate"]["git_commit"],
        "document_count": len(manifest["documents"]),
        "scenario_count": questions["scenario_count"],
        "expression_count": len(expressions),
        "embedding_batch_calls": 2,
        "answer_generation_calls": len(expressions),
        "classification_calls": len(expressions),
        "version_resolution_calls_max": len(expressions),
        "max_logical_external_calls": policy["max_logical_external_calls"],
        "retry_count": policy["retry_count"],
        "max_cost_usd": policy["max_cost_usd"],
        "stop_on_provider_error": policy["stop_on_provider_error"],
        "gold_available_to_runner": policy["gold_available_to_runner"],
    }


def _verify_sealed_documents(
    manifest: dict[str, Any], sealed_documents_dir: Path
) -> list[Path]:
    paths = []
    for document in manifest["documents"]:
        path = sealed_documents_dir / f"{document['document_id']}.md"
        if not path.is_file():
            raise ValueError(f"sealed documentがありません: {path}")
        if _sha256(path) != document["sha256"]:
            raise ValueError(f"sealed documentのhashが一致しません: {document['document_id']}")
        paths.append(path)
    return paths


def _all_query_texts(expressions: list[dict[str, str]]) -> list[str]:
    texts: list[str] = []
    for expression in expressions:
        question = expression["question"]
        for text in decompose_query(question):
            if text not in texts:
                texts.append(text)
    return texts


def _usage(logger: EvaluationLogger, result: dict[str, Any] | None) -> tuple[int, int]:
    input_tokens = int(logger.generation.get("input_tokens", 0)) + int(
        logger.classification.get("input_tokens", 0)
    )
    output_tokens = int(logger.generation.get("output_tokens", 0)) + int(
        logger.classification.get("output_tokens", 0)
    )
    resolver = result.get("version_resolution", {}) if result else {}
    input_tokens += int(resolver.get("input_tokens", 0))
    output_tokens += int(resolver.get("output_tokens", 0))
    return input_tokens, output_tokens


def _logical_calls(logger: HoldoutEvaluationLogger) -> int:
    calls = 1  # generation attempt
    if logger.generation.get("status") == "SUCCESS":
        calls += 1  # classification attempt
    calls += max(0, len(logger.classification_attempts) - 1)  # resolver attempt
    return calls


def _retrieval_rows(logger: EvaluationLogger) -> list[dict[str, Any]]:
    return [
        {
            "rank": hit.rank,
            "score": hit.score,
            "document_id": hit.element.metadata.get("document_key"),
            "heading": hit.element.heading,
            "element_id": str(hit.element.id),
        }
        for hit in logger.retrieval_hits
    ]


def run_predictions(
    *,
    manifest_path: Path,
    candidate_path: Path,
    questions_path: Path,
    sealed_documents_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {output_dir}")
    manifest = _read_json(manifest_path)
    candidate = _read_json(candidate_path)
    questions = _read_json(questions_path)
    plan = build_plan(manifest, candidate, questions)
    paths = _verify_sealed_documents(manifest, sealed_documents_dir)
    expressions = _expressions(questions)

    output_dir.mkdir(parents=True)
    run_id = f"text-holdout-v1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    run_manifest = {
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "public_manifest_path": _portable_path(manifest_path),
        "public_manifest_sha256": _sha256(manifest_path),
        "candidate_config_path": _portable_path(candidate_path),
        "candidate_config_sha256": _sha256(candidate_path),
        "questions_path": _portable_path(questions_path),
        "questions_sha256": _sha256(questions_path),
        "sealed_document_hashes_verified": True,
        "sealed_gold_opened": False,
        **plan,
    }
    _write_json(output_dir / "run_manifest.json", run_manifest)

    elements = [element for path in paths for element in build_markdown_elements(path)]
    embeddings = get_embeddings()
    document_vectors = embeddings.embed_documents(
        [contextual_heading_document_text(element) for element in elements],
        task_type=candidate["pipeline"]["embedding"]["document_task_type"],
    )
    query_texts = _all_query_texts(expressions)
    query_vectors = embeddings.embed_documents(
        query_texts,
        task_type=candidate["pipeline"]["embedding"]["query_task_type"],
    )
    vectors = dict(zip(query_texts, query_vectors, strict=True))

    base_index = QdrantVectorIndex(
        client=QdrantClient(":memory:"), collection_name=run_id
    )
    base_index.ensure_collection(len(document_vectors[0]))
    base_index.upsert(elements, document_vectors, "text-holdout-candidate-v1")
    index = QuestionAwareIndex(base_index, vectors, decompose=True)

    generator_model = candidate["pipeline"]["generation"]["model"]
    classifier_model = candidate["pipeline"]["classification"]["model"]
    generator = _provider(generator_model)
    classifier = _provider(classifier_model)
    resolver = _provider(classifier_model)
    top_k = int(candidate["pipeline"]["retrieval"]["top_k"])
    threshold = float(
        candidate["pipeline"]["classification"]["version_resolver"][
            "confidence_threshold"
        ]
    )

    records: list[dict[str, Any]] = []
    total_input_tokens = 0
    total_output_tokens = 0
    logical_calls = 2
    stop_reason = "COMPLETED"
    for expression in expressions:
        current_cost = (
            token_cost_usd(total_input_tokens, total_output_tokens)
            + EMBEDDING_COST_RESERVE_USD
        )
        if current_cost + RESERVE_USD_PER_EXPRESSION > plan["max_cost_usd"]:
            stop_reason = "COST_LIMIT_REACHED"
            break
        if logical_calls + 3 > plan["max_logical_external_calls"]:
            stop_reason = "CALL_LIMIT_REACHED"
            break

        question = expression["question"]
        index.select_question(question)
        logger = HoldoutEvaluationLogger()
        started = time.perf_counter()
        result = None
        error = None
        try:
            result = answer_question(
                question,
                embed_query=lambda value: vectors[value],
                vector_index=index,
                generator=generator,
                classifier=classifier,
                version_resolver=resolver,
                event_logger=logger,
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                version_resolution_schema=load_schema(VERSION_SCHEMA),
                top_k=top_k,
                version_resolution_confidence_threshold=threshold,
                generation_prompt_builder=build_temporal_generation_prompt,
                generation_prompt_version=TEMPORAL_GENERATION_PROMPT_VERSION,
            )
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"

        expression_input, expression_output = _usage(logger, result)
        total_input_tokens += expression_input
        total_output_tokens += expression_output
        logical_calls += _logical_calls(logger)
        records.append(
            {
                **expression,
                "status": "SUCCESS" if result else "FAILED",
                "answer_label": result["answer_label"] if result else None,
                "answer": result["answer"] if result else None,
                "claims": result["claims"] if result else [],
                "classification_factors": logger.classification.get("factors"),
                "version_resolution": result.get("version_resolution") if result else None,
                "retrieved": _retrieval_rows(logger),
                "input_tokens": expression_input,
                "output_tokens": expression_output,
                "cost_usd": token_cost_usd(expression_input, expression_output),
                "elapsed_seconds": time.perf_counter() - started,
                "error": error,
            }
        )
        _write_jsonl(output_dir / "predictions.jsonl", records)
        if error and _provider_error(error):
            stop_reason = "PROVIDER_ERROR_FAIL_FAST"
            break

    summary = {
        "run_id": run_id,
        "stop_reason": stop_reason,
        "prediction_count": len(records),
        "success_count": sum(record["status"] == "SUCCESS" for record in records),
        "failure_count": sum(record["status"] == "FAILED" for record in records),
        "logical_external_calls": logical_calls,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_usd": token_cost_usd(total_input_tokens, total_output_tokens),
        "embedding_cost_reserve_usd": EMBEDDING_COST_RESERVE_USD,
        "estimated_total_cost_usd": (
            token_cost_usd(total_input_tokens, total_output_tokens)
            + EMBEDDING_COST_RESERVE_USD
        ),
        "sealed_gold_opened": False,
        "predictions_sha256": _sha256(output_dir / "predictions.jsonl"),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def freeze_predictions(
    *, manifest_path: Path, predictions_path: Path, summary_path: Path
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    if manifest["state"] != "CANDIDATE_FROZEN":
        raise ValueError("freezeにはCANDIDATE_FROZEN stateが必要です")
    if summary["stop_reason"] != "COMPLETED":
        raise ValueError("完了していないrunはfreezeできません")
    records = [
        json.loads(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected = manifest["questions"]["expression_count"]
    keys = {(row["scenario_id"], row["variant_type"]) for row in records}
    if len(records) != expected or len(keys) != expected:
        raise ValueError("predictionは100件の一意な表現である必要があります")
    manifest["state"] = "PREDICTIONS_FROZEN"
    manifest["predictions"] = {
        "run_id": summary["run_id"],
        "sha256": _sha256(predictions_path),
        "attempt_count": len(records),
        "frozen_at": datetime.now(UTC).isoformat(),
    }
    _write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    plan_parser.add_argument("--candidate", type=Path, default=DEFAULT_CONFIG)
    plan_parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    run_parser.add_argument("--candidate", type=Path, default=DEFAULT_CONFIG)
    run_parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    run_parser.add_argument("--sealed-documents-dir", type=Path, required=True)
    run_parser.add_argument("--output-dir", type=Path, required=True)
    freeze_parser = subparsers.add_parser("freeze")
    freeze_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    freeze_parser.add_argument("--predictions", type=Path, required=True)
    freeze_parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "plan":
        plan = build_plan(
            _read_json(args.manifest),
            _read_json(args.candidate),
            _read_json(args.questions),
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "freeze":
        manifest = freeze_predictions(
            manifest_path=args.manifest,
            predictions_path=args.predictions,
            summary_path=args.summary,
        )
        print(json.dumps(manifest["predictions"], ensure_ascii=False, indent=2))
        return 0
    summary = run_predictions(
        manifest_path=args.manifest,
        candidate_path=args.candidate,
        questions_path=args.questions,
        sealed_documents_dir=args.sealed_documents_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["stop_reason"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
