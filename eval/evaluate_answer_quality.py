from pathlib import Path
import argparse
import csv
import re
import time

from src.rag_chain import generate_answer


EVALUATION_FILE = Path("eval/evaluation_questions_hard.csv")
OUTPUT_FILE = Path("eval/results/hard_answer_quality.csv")
VALID_ANSWER_TYPES = {"根拠十分", "判断要", "文書不足"}
RESULT_FIELDS = [
    "question_id",
    "question",
    "difficulty",
    "expected_answer_type",
    "predicted_answer_type",
    "classification_ok",
    "content_ok",
    "no_hallucination",
    "review_status",
    "answer",
    "retrieved_document_ids",
    "retrieved_headings",
    "generation_error",
    "elapsed_seconds",
    "memo",
]


def load_evaluation_questions(file_path: Path) -> list[dict]:
    """回答品質評価用CSVを読み込む。"""
    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def extract_answer_type(answer: str) -> str:
    """LLM回答本文の「回答分類」から3分類のいずれかを抽出する。"""
    match = re.search(r"回答分類[:：]\s*(根拠十分|判断要|文書不足)", answer)
    return match.group(1) if match else "抽出失敗"


def _reference_heading(reference: dict) -> str:
    return str(reference.get("heading") or "")


def evaluate_answer_quality(
    questions: list[dict], generate_fn=None, delay_seconds: float = 0
) -> list[dict]:
    """
    回答分類を自動評価し、人手で内容を確認するための記録を作る。

    content_ok と no_hallucination は回答本文を根拠文書と照合する必要があるため、
    自動判定せず空欄にする。
    """
    if not questions:
        raise ValueError("評価質問がありません")
    if generate_fn is None:
        generate_fn = generate_answer

    records = []
    seen_ids = set()
    for index, row in enumerate(questions):
        # 旧15問セットにはIDがないため、行順から互換用IDを付ける。
        question_id = row.get("question_id", "").strip() or f"row-{index + 1:03d}"
        question = row.get("question", "").strip()
        expected_answer_type = row.get("expected_answer_type", "").strip()
        if question_id in seen_ids:
            raise ValueError(f"質問IDが重複しています: {question_id}")
        if not question:
            raise ValueError(f"質問文がありません: {question_id}")
        if expected_answer_type not in VALID_ANSWER_TYPES:
            raise ValueError(f"期待分類が不正です: {question_id}")
        seen_ids.add(question_id)

        started_at = time.perf_counter()
        answer = ""
        references = []
        generation_error = ""
        try:
            result = generate_fn(question)
            answer = str(result.get("answer", ""))
            references = result.get("references", [])
        except Exception as error:  # 評価を途中で失わず、質問ごとの失敗として残す。
            generation_error = f"{type(error).__name__}: {error}"
        elapsed_seconds = time.perf_counter() - started_at

        predicted_answer_type = (
            extract_answer_type(answer) if not generation_error else "生成失敗"
        )
        record = {
            "question_id": question_id,
            "question": question,
            "difficulty": row.get("difficulty", ""),
            "expected_answer_type": expected_answer_type,
            "predicted_answer_type": predicted_answer_type,
            "classification_ok": int(
                predicted_answer_type == expected_answer_type
            ),
            "content_ok": "",
            "no_hallucination": "",
            "review_status": "pending",
            "answer": answer,
            "retrieved_document_ids": "|".join(
                str(reference.get("document_id") or "") for reference in references
            ),
            "retrieved_headings": "|".join(
                _reference_heading(reference) for reference in references
            ),
            "generation_error": generation_error,
            "elapsed_seconds": f"{elapsed_seconds:.3f}",
            "memo": "",
        }
        records.append(record)

        print("=" * 80)
        print(f"質問ID: {question_id}")
        print(f"質問: {question}")
        print(f"期待分類: {expected_answer_type}")
        print(f"予測分類: {predicted_answer_type}")
        print(f"分類一致: {bool(record['classification_ok'])}")
        if generation_error:
            print(f"生成エラー: {generation_error}")

        if delay_seconds > 0 and index < len(questions) - 1:
            time.sleep(delay_seconds)

    correct = sum(record["classification_ok"] for record in records)
    print("\n" + "=" * 80)
    print("回答品質評価（自動判定部分）")
    print("=" * 80)
    print(f"評価質問数: {len(records)}")
    print(f"分類一致: {correct}/{len(records)}")
    print("内容妥当性と幻覚有無は、保存したCSVを根拠文書と照合して判定してください。")
    return records


def save_results(records: list[dict], output_path: Path) -> None:
    """質問ごとの回答とレビュー欄をCSVに保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="回答分類を自動評価し、人手レビュー用CSVを作る"
    )
    parser.add_argument("--input", type=Path, default=EVALUATION_FILE)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    parser.add_argument(
        "--question-id",
        action="append",
        help="指定した質問IDだけを実行する。複数回指定可能",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=5,
        help="APIの連続呼び出し間隔。テスト時は0を指定できる",
    )
    parser.add_argument(
        "--method",
        choices=("vector", "contextual"),
        default="vector",
        help="回答生成に使う検索方式",
    )
    args = parser.parse_args()

    questions = load_evaluation_questions(args.input)
    if args.question_id:
        requested_ids = set(args.question_id)
        questions = [
            row for row in questions if row.get("question_id") in requested_ids
        ]
        found_ids = {row["question_id"] for row in questions}
        if found_ids != requested_ids:
            missing = sorted(requested_ids - found_ids)
            parser.error(f"質問IDが見つかりません: {missing}")
    generate_fn = None
    if args.method == "contextual":
        from eval.contextual_answer import generate_contextual_answer

        generate_fn = generate_contextual_answer

    records = evaluate_answer_quality(
        questions,
        generate_fn=generate_fn,
        delay_seconds=args.delay_seconds,
    )
    save_results(records, args.output)
    print(f"結果CSV: {args.output}")


if __name__ == "__main__":
    main()
