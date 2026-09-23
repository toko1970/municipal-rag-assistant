"""固定した質問・検索結果で回答生成モデルを比較する。"""

from datetime import datetime
from pathlib import Path
import argparse
import csv
import json
import time

from eval.evaluate_answer_quality import extract_answer_type
from src.llm_provider import create_provider
from src.rag_chain import build_context, build_prompt, build_references
from src.retriever import retrieve_documents_with_score


EVALUATION_FILE = Path("eval/evaluation_questions_500.csv")
RETRIEVAL_CACHE_FILE = Path("eval/results/model_evaluation_retrieval.jsonl")
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5-mini",
    "mistral": "mistral-small-latest",
}
PRICING_PER_MILLION = {
    ("gemini", "gemini-2.5-flash"): (0.30, 2.50),
    ("gemini", "gemini-3.1-flash-lite"): (0.25, 1.50),
    ("gemini", "gemini-3.5-flash-lite"): (0.30, 2.50),
    ("openai", "gpt-5-mini"): (0.25, 2.00),
    ("mistral", "mistral-small-latest"): (0.15, 0.60),
}
RESULT_FIELDS = (
    "question_id",
    "scenario_id",
    "question",
    "topic",
    "difficulty",
    "variant_type",
    "expected_answer_type",
    "expected_answer_key",
    "provider",
    "requested_model",
    "model",
    "predicted_answer_type",
    "classification_ok",
    "answer",
    "retrieved_document_ids",
    "retrieved_headings",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "elapsed_seconds",
    "request_id",
    "retrieval_error",
    "generation_error",
    "executed_at",
)


def load_questions(path: Path, variant: str = "formal") -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if {row.get("review_status") for row in rows} != {"user_approved"}:
        raise ValueError("user_approvedで固定された評価セットを指定してください")
    if variant != "all":
        rows = [row for row in rows if row.get("variant_type") == variant]
    return rows


def load_retrieval_cache(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    cache = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                cache[record["question_id"]] = record
    return cache


def save_retrieval_cache(cache: dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in cache.values():
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def prepare_retrieval_cases(
    questions: list[dict],
    cache_path: Path,
    retrieve_fn=retrieve_documents_with_score,
) -> dict[str, dict]:
    cache = load_retrieval_cache(cache_path)
    for row in questions:
        question_id = row["question_id"]
        if question_id in cache and not cache[question_id].get("retrieval_error"):
            continue
        try:
            results = retrieve_fn(row["question"])
            cache[question_id] = {
                "question_id": question_id,
                "question": row["question"],
                "context": build_context(results),
                "references": build_references(results),
                "retrieval_error": "",
            }
        except Exception as error:
            cache[question_id] = {
                "question_id": question_id,
                "question": row["question"],
                "context": "",
                "references": [],
                "retrieval_error": f"{type(error).__name__}: {error}",
            }
        save_retrieval_cache(cache, cache_path)
    return cache


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int):
    rates = PRICING_PER_MILLION.get((provider, model))
    if rates is None:
        return ""
    input_rate, output_rate = rates
    return f"{(input_tokens * input_rate + output_tokens * output_rate) / 1_000_000:.8f}"


def save_results(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def load_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def evaluate_questions(
    questions: list[dict],
    retrieval_cache: dict[str, dict],
    provider,
    output_path: Path,
    resume: bool = True,
    retry_errors: bool = False,
    delay_seconds: float = 0,
) -> list[dict]:
    existing = load_results(output_path) if resume else []
    records_by_id = {row["question_id"]: row for row in existing}

    for index, row in enumerate(questions):
        question_id = row["question_id"]
        previous = records_by_id.get(question_id)
        if previous and (not retry_errors or not previous.get("generation_error")):
            continue

        cached = retrieval_cache[question_id]
        references = cached.get("references", [])
        started_at = time.perf_counter()
        answer = ""
        generation_error = ""
        metadata = {
            "provider": provider.provider_name,
            "model": provider.model,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "request_id": "",
        }
        if not cached.get("retrieval_error"):
            try:
                response = provider.generate(
                    build_prompt(row["question"], cached["context"])
                )
                answer = response.text
                metadata = response.metadata()
            except Exception as error:
                generation_error = f"{type(error).__name__}: {error}"
        elapsed = time.perf_counter() - started_at
        predicted = extract_answer_type(answer) if answer else "生成失敗"
        input_tokens = int(metadata.get("input_tokens") or 0)
        output_tokens = int(metadata.get("output_tokens") or 0)
        result = {
            "question_id": question_id,
            "scenario_id": row.get("scenario_id", ""),
            "question": row["question"],
            "topic": row.get("topic", ""),
            "difficulty": row.get("difficulty", ""),
            "variant_type": row.get("variant_type", ""),
            "expected_answer_type": row["expected_answer_type"],
            "expected_answer_key": row.get("expected_answer_key", ""),
            "provider": metadata["provider"],
            "requested_model": provider.model,
            "model": metadata["model"],
            "predicted_answer_type": predicted,
            "classification_ok": int(predicted == row["expected_answer_type"]),
            "answer": answer,
            "retrieved_document_ids": "|".join(
                str(reference.get("document_id") or "") for reference in references
            ),
            "retrieved_headings": "|".join(
                str(reference.get("heading") or "") for reference in references
            ),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": int(metadata.get("total_tokens") or 0),
            "estimated_cost_usd": estimate_cost(
                metadata["provider"], provider.model, input_tokens, output_tokens
            ),
            "elapsed_seconds": f"{elapsed:.3f}",
            "request_id": metadata.get("request_id", ""),
            "retrieval_error": cached.get("retrieval_error", ""),
            "generation_error": generation_error,
            "executed_at": datetime.now().isoformat(timespec="seconds"),
        }
        records_by_id[question_id] = result
        ordered = [records_by_id[item["question_id"]] for item in questions if item["question_id"] in records_by_id]
        save_results(ordered, output_path)
        print(
            f"{question_id}: {predicted} / {row['expected_answer_type']} "
            f"({metadata['provider']}/{metadata['model']})"
        )
        if delay_seconds > 0 and index < len(questions) - 1:
            time.sleep(delay_seconds)

    return [
        records_by_id[row["question_id"]]
        for row in questions
        if row["question_id"] in records_by_id
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="同じ検索結果で回答生成モデルを比較する")
    parser.add_argument("--provider", choices=DEFAULT_MODELS, required=True)
    parser.add_argument("--model")
    parser.add_argument("--input", type=Path, default=EVALUATION_FILE)
    parser.add_argument("--retrieval-cache", type=Path, default=RETRIEVAL_CACHE_FILE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--variant", default="formal")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay-seconds", type=float, default=1)
    parser.add_argument("--prepare-retrieval-only", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()

    model = args.model or DEFAULT_MODELS[args.provider]
    questions = load_questions(args.input, args.variant)
    if args.limit:
        questions = questions[: args.limit]
    cache = prepare_retrieval_cases(questions, args.retrieval_cache)
    if args.prepare_retrieval_only:
        print(f"検索結果を保存しました: {args.retrieval_cache}")
        return

    output = args.output or Path(
        f"eval/results/model_{args.provider}_{model}_{args.variant}.csv"
    )
    provider = create_provider(args.provider, model)
    records = evaluate_questions(
        questions,
        cache,
        provider,
        output,
        resume=not args.no_resume,
        retry_errors=args.retry_errors,
        delay_seconds=args.delay_seconds,
    )
    correct = sum(int(row["classification_ok"]) for row in records)
    print(f"分類一致: {correct}/{len(records)}")
    print(f"結果: {output}")


if __name__ == "__main__":
    main()
