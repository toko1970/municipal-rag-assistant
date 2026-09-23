from collections import Counter
from pathlib import Path
import argparse
import csv


TRUE_VALUES = {"1", "true", "yes"}
FALSE_VALUES = {"0", "false", "no"}
FAILURE_LABELS = {
    "success": "成功",
    "retrieval_failure": "検索失敗",
    "answer_generation_failure": "回答生成失敗",
    "classification_failure": "回答分類失敗",
    "generation_error": "回答生成エラー",
    "unanswerable_handled": "文書に根拠なし・適切に回答抑制",
    "unanswerable_failed": "文書に根拠なし・回答抑制失敗",
}
OUTPUT_FIELDS = [
    "question_id",
    "question",
    "expected_answer_type",
    "evidence_hit_at_5",
    "classification_ok",
    "content_ok",
    "no_hallucination",
    "failure_category",
]


def load_csv(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"結果がありません: {path}")
    if any(not row.get("question_id") for row in rows):
        raise ValueError(f"質問IDがない結果があります: {path}")
    records = {row["question_id"]: row for row in rows}
    if len(records) != len(rows):
        raise ValueError(f"質問IDが重複しています: {path}")
    return records


def parse_review_bool(value: str, field: str, question_id: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"{question_id} の {field} が未判定または不正です")


def classify_failure(answer: dict, retrieval: dict) -> str:
    """検索・回答・分類を順に確認し、質問を排他的な1区分へ分類する。"""
    question_id = answer["question_id"]
    if answer.get("generation_error"):
        return "generation_error"

    classification_ok = answer.get("classification_ok") == "1"
    content_ok = parse_review_bool(answer.get("content_ok", ""), "content_ok", question_id)
    no_hallucination = parse_review_bool(
        answer.get("no_hallucination", ""), "no_hallucination", question_id
    )

    if answer.get("expected_answer_type") == "文書不足":
        return (
            "unanswerable_handled"
            if classification_ok and content_ok and no_hallucination
            else "unanswerable_failed"
        )

    if retrieval.get("evidence_hit_at_5") != "1":
        return "retrieval_failure"
    if not content_ok or not no_hallucination:
        return "answer_generation_failure"
    if not classification_ok:
        return "classification_failure"
    return "success"


def summarize_failures(
    answers: dict[str, dict], retrievals: dict[str, dict]
) -> tuple[list[dict], Counter]:
    if set(answers) != set(retrievals):
        missing_answers = sorted(set(retrievals) - set(answers))
        missing_retrievals = sorted(set(answers) - set(retrievals))
        raise ValueError(
            "質問IDが一致しません: "
            f"回答なし={missing_answers}, 検索結果なし={missing_retrievals}"
        )

    records = []
    counts = Counter()
    for question_id, answer in answers.items():
        retrieval = retrievals[question_id]
        if answer.get("question") != retrieval.get("question"):
            raise ValueError(f"質問文が一致しません: {question_id}")
        category = classify_failure(answer, retrieval)
        counts[category] += 1
        records.append(
            {
                "question_id": question_id,
                "question": answer["question"],
                "expected_answer_type": answer["expected_answer_type"],
                "evidence_hit_at_5": retrieval.get("evidence_hit_at_5", ""),
                "classification_ok": answer.get("classification_ok", ""),
                "content_ok": answer.get("content_ok", ""),
                "no_hallucination": answer.get("no_hallucination", ""),
                "failure_category": category,
            }
        )
    return records, counts


def save_results(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="検索結果と人手確認済み回答を結合し、失敗原因を集計する"
    )
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records, counts = summarize_failures(
        load_csv(args.answers),
        load_csv(args.retrieval),
    )
    save_results(records, args.output)

    print("失敗原因 | 件数")
    print("--- | ---:")
    for category in FAILURE_LABELS:
        if counts[category]:
            print(f"{FAILURE_LABELS[category]} | {counts[category]}")
    print(f"結果CSV: {args.output}")


if __name__ == "__main__":
    main()
