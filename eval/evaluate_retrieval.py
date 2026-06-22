from pathlib import Path
import csv

from src.retriever import retrieve_documents_with_score


# EVALUATION_FILE = Path("eval/evaluation_questions.csv")
EVALUATION_FILE = Path("eval/evaluation_questions_practical.csv")
TOP_K = 5


def load_evaluation_questions(file_path: Path) -> list[dict]:
    """
    評価用CSVを読み込む。
    """
    with file_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def evaluate_retrieval(questions: list[dict]) -> None:
    """
    Recall@1 / Recall@3 / Recall@5 を評価する。
    """
    total = len(questions)

    hit_at_1 = 0
    hit_at_3 = 0
    hit_at_5 = 0

    for row in questions:
        question = row["question"]
        expected_document_id = row["expected_document_id"]

        results = retrieve_documents_with_score(
            query=question,
            top_k=TOP_K,
        )

        retrieved_document_ids = [
            doc.metadata.get("document_id")
            for doc, score in results
        ]

        is_hit_at_1 = expected_document_id in retrieved_document_ids[:1]
        is_hit_at_3 = expected_document_id in retrieved_document_ids[:3]
        is_hit_at_5 = expected_document_id in retrieved_document_ids[:5]

        hit_at_1 += int(is_hit_at_1)
        hit_at_3 += int(is_hit_at_3)
        hit_at_5 += int(is_hit_at_5)

        print("=" * 80)
        print(f"質問: {question}")
        print(f"正解文書: {expected_document_id}")
        print(f"検索結果: {retrieved_document_ids}")
        print(f"Hit@1: {is_hit_at_1}")
        print(f"Hit@3: {is_hit_at_3}")
        print(f"Hit@5: {is_hit_at_5}")

    print("\n" + "=" * 80)
    print("検索性能評価結果")
    print("=" * 80)
    print(f"評価質問数: {total}")
    print(f"Recall@1: {hit_at_1 / total:.2f} ({hit_at_1}/{total})")
    print(f"Recall@3: {hit_at_3 / total:.2f} ({hit_at_3}/{total})")
    print(f"Recall@5: {hit_at_5 / total:.2f} ({hit_at_5}/{total})")


def main():
    questions = load_evaluation_questions(EVALUATION_FILE)
    evaluate_retrieval(questions)


if __name__ == "__main__":
    main()