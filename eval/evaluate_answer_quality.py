from pathlib import Path
import csv
import re
import time

from src.rag_chain import generate_answer


EVALUATION_FILE = Path("eval/answer_quality_questions.csv")


def load_evaluation_questions(file_path: Path) -> list[dict]:
    """
    回答品質評価用CSVを読み込む。
    """
    with file_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def extract_answer_type(answer: str) -> str:
    """
    LLM回答本文から回答分類を抽出する。
    想定形式:
    回答分類: 根拠十分
    """
    match = re.search(r"回答分類[:：]\s*(根拠十分|判断要|文書不足)", answer)

    if match:
        return match.group(1)

    return "抽出失敗"


def evaluate_answer_quality(questions: list[dict]) -> None:
    """
    回答分類の正答率を評価する。
    """
    total = len(questions)
    correct = 0

    for row in questions:
        question = row["question"]
        expected_answer_type = row["expected_answer_type"]

        try:
            result = generate_answer(question)
        except Exception as e:
            print("=" * 80)
            print(f"質問: {question}")
            print("エラーが発生しました")
            print(e)
            continue

        answer = result["answer"]
        predicted_answer_type = extract_answer_type(answer)

        is_correct = predicted_answer_type == expected_answer_type
        correct += int(is_correct)

        print("=" * 80)
        print(f"質問: {question}")
        print(f"期待分類: {expected_answer_type}")
        print(f"予測分類: {predicted_answer_type}")
        print(f"正誤: {is_correct}")
        print("-" * 80)
        print(answer)

        time.sleep(5)

    print("\n" + "=" * 80)
    print("回答品質評価結果")
    print("=" * 80)
    print(f"評価質問数: {total}")
    print(f"分類正答数: {correct}/{total}")
    print(f"回答分類精度: {correct / total:.2f}")


def main():
    questions = load_evaluation_questions(EVALUATION_FILE)
    evaluate_answer_quality(questions)


if __name__ == "__main__":
    main()