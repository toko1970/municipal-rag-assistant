"""Paired end-to-end regression gate for the contextual heading candidate."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from config import (
    BASE_DIR,
    CLASSIFIER_MODEL_NAME,
    LLM_MODEL_NAME,
    QDRANT_COLLECTION_NAME,
    TOP_K,
)
from eval.compare_contextual_heading import (
    COLLECTION_NAME,
    load_baseline_query_vectors,
)
from eval.compare_retrieval import load_results as load_retrieval_results
from eval.evaluate_models import is_rate_limit_error, load_questions
from src.llm_provider import GeminiProvider
from src.qdrant_index import QdrantVectorIndex
from src.query_service import answer_question, load_schema


ANSWER_SCHEMA_PATH = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA_PATH = (
    BASE_DIR / "design/schemas/classification-output-v1.schema.json"
)
RESULT_FIELDS = (
    "question_id",
    "retrieval_variant",
    "question",
    "expected_answer_type",
    "expected_answer_key",
    "answer_label",
    "classification_ok",
    "content_key_ok",
    "support_gate_ok",
    "answer",
    "visible_claims",
    "classification_factors",
    "retrieved_document_ids",
    "retrieved_headings",
    "generation_input_tokens",
    "generation_output_tokens",
    "classification_input_tokens",
    "classification_output_tokens",
    "elapsed_seconds",
    "error",
)


def changed_evidence_at_5_ids(baseline_path: Path, candidate_path: Path) -> list[str]:
    baseline = load_retrieval_results(baseline_path)
    candidate = load_retrieval_results(candidate_path)
    if set(baseline) != set(candidate):
        raise ValueError("baselineとcandidateの質問IDが一致しません")
    return [
        question_id
        for question_id in baseline
        if baseline[question_id].get("evidence_hit_at_5")
        != candidate[question_id].get("evidence_hit_at_5")
    ]


def load_criteria(path: Path, expected_ids: list[str]) -> dict[str, dict]:
    criteria = json.loads(path.read_text(encoding="utf-8"))
    if set(criteria) != set(expected_ids):
        raise ValueError("内容判定基準の質問IDが比較対象と一致しません")
    for question_id, rule in criteria.items():
        if set(rule) != {"required_patterns", "ordered_patterns"}:
            raise ValueError(f"内容判定基準の項目が不正です: {question_id}")
        for pattern in [*rule["required_patterns"], *rule["ordered_patterns"]]:
            re.compile(pattern)
    return criteria


def content_key_ok(answer: str, rule: dict) -> bool:
    if not all(re.search(pattern, answer) for pattern in rule["required_patterns"]):
        return False
    position = 0
    for pattern in rule["ordered_patterns"]:
        match = re.search(pattern, answer[position:])
        if match is None:
            return False
        position += match.end()
    return True


@dataclass
class EvaluationLogger:
    request_id: UUID = field(default_factory=uuid4)
    retrieval_hits: list = field(default_factory=list)
    generation: dict = field(default_factory=dict)
    classification: dict = field(default_factory=dict)
    answer_result: dict = field(default_factory=dict)

    def start_request(self, _question: str) -> UUID:
        return self.request_id

    def record_retrieval(self, _request_id: UUID, hits: list) -> None:
        self.retrieval_hits = hits

    def record_generation_attempt(self, _request_id: UUID, **kwargs) -> UUID:
        self.generation = kwargs
        return uuid4()

    def record_classification_attempt(self, _request_id: UUID, **kwargs) -> UUID:
        self.classification = kwargs
        return uuid4()

    def record_answer_result(self, _request_id: UUID, **kwargs) -> UUID:
        self.answer_result = kwargs
        return uuid4()


def load_existing(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    return {(row["question_id"], row["retrieval_variant"]): row for row in rows}


def save_results(records: dict[tuple[str, str], dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records.values())


def evaluate_pair(
    questions: list[dict],
    *,
    query_vectors: dict[str, list[float]],
    criteria: dict[str, dict],
    output_path: Path,
    delay_seconds: float,
) -> dict[tuple[str, str], dict]:
    records = load_existing(output_path)
    generator = GeminiProvider(LLM_MODEL_NAME)
    classifier = GeminiProvider(CLASSIFIER_MODEL_NAME)
    answer_schema = load_schema(ANSWER_SCHEMA_PATH)
    classification_schema = load_schema(CLASSIFICATION_SCHEMA_PATH)
    indexes = {
        "baseline": QdrantVectorIndex(collection_name=QDRANT_COLLECTION_NAME),
        "contextual_heading": QdrantVectorIndex(collection_name=COLLECTION_NAME),
    }

    for row in questions:
        for variant, index in indexes.items():
            key = (row["question_id"], variant)
            if key in records:
                continue
            logger = EvaluationLogger()
            started = time.perf_counter()
            error = ""
            result = None
            try:
                result = answer_question(
                    row["question"],
                    embed_query=lambda question: query_vectors[question],
                    vector_index=index,
                    generator=generator,
                    classifier=classifier,
                    event_logger=logger,
                    answer_schema=answer_schema,
                    classification_schema=classification_schema,
                    top_k=TOP_K,
                )
            except Exception as exception:
                error = f"{type(exception).__name__}: {exception}"
            elapsed = time.perf_counter() - started
            answer = result["answer"] if result else ""
            if result:
                label = result["answer_label"]
            elif logger.generation.get("status") == "SUCCESS":
                label = "分類・表示失敗"
            else:
                label = "生成失敗"
            factors = logger.classification.get("factors") or {}
            visible_claims = logger.answer_result.get("claims") or []
            record = {
                "question_id": row["question_id"],
                "retrieval_variant": variant,
                "question": row["question"],
                "expected_answer_type": row["expected_answer_type"],
                "expected_answer_key": row["expected_answer_key"],
                "answer_label": label,
                "classification_ok": int(label == row["expected_answer_type"]),
                "content_key_ok": int(
                    bool(result) and content_key_ok(answer, criteria[row["question_id"]])
                ),
                "support_gate_ok": int(
                    bool(result)
                    and (
                        not visible_claims
                        or bool(factors.get("answer_fully_supported"))
                    )
                ),
                "answer": answer,
                "visible_claims": json.dumps(
                    visible_claims, ensure_ascii=False, default=str
                ),
                "classification_factors": json.dumps(factors, ensure_ascii=False),
                "retrieved_document_ids": "|".join(
                    str(hit.element.metadata.get("document_id", ""))
                    for hit in logger.retrieval_hits
                ),
                "retrieved_headings": "|".join(
                    " > ".join(
                        str(hit.element.metadata[key])
                        for key in ("見出し1", "見出し2", "見出し3")
                        if hit.element.metadata.get(key)
                    )
                    for hit in logger.retrieval_hits
                ),
                "generation_input_tokens": logger.generation.get("input_tokens", 0),
                "generation_output_tokens": logger.generation.get("output_tokens", 0),
                "classification_input_tokens": logger.classification.get(
                    "input_tokens", 0
                ),
                "classification_output_tokens": logger.classification.get(
                    "output_tokens", 0
                ),
                "elapsed_seconds": f"{elapsed:.3f}",
                "error": error,
            }
            records[key] = record
            save_results(records, output_path)
            print(
                f"{row['question_id']} {variant}: label={label}, "
                f"content={bool(record['content_key_ok'])}, error={error or 'none'}"
            )
            if is_rate_limit_error(error):
                return records
            if delay_seconds:
                time.sleep(delay_seconds)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--baseline-retrieval", type=Path, required=True)
    parser.add_argument("--candidate-retrieval", type=Path, required=True)
    parser.add_argument("--query-cache", type=Path, required=True)
    parser.add_argument("--criteria", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=1)
    args = parser.parse_args()

    changed_ids = changed_evidence_at_5_ids(
        args.baseline_retrieval, args.candidate_retrieval
    )
    criteria = load_criteria(args.criteria, changed_ids)
    questions_by_id = {
        row["question_id"]: row for row in load_questions(args.input, "formal")
    }
    questions = [questions_by_id[question_id] for question_id in changed_ids]
    query_vectors = load_baseline_query_vectors(args.query_cache, questions)
    records = evaluate_pair(
        questions,
        query_vectors=query_vectors,
        criteria=criteria,
        output_path=args.output,
        delay_seconds=args.delay_seconds,
    )
    completed = [row for row in records.values() if not row["error"]]
    print(
        json.dumps(
            {
                "target_questions": changed_ids,
                "completed": len(completed),
                "classification_ok": sum(
                    int(row["classification_ok"]) for row in completed
                ),
                "content_key_ok": sum(int(row["content_key_ok"]) for row in completed),
                "support_gate_ok": sum(
                    int(row["support_gate_ok"]) for row in completed
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
