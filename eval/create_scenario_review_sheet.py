"""100シナリオの人手レビュー用CSVを作成する。"""

from pathlib import Path
import csv

from eval.generate_large_evaluation_set import generate_records


OUTPUT_FILE = Path("eval/evaluation_scenario_review.csv")
FIELDS = (
    "scenario_id",
    "topic",
    "difficulty",
    "formal_question",
    "expected_answer_type",
    "expected_answer_key",
    "expected_evidence",
    "assistant_decision",
    "review_priority",
    "assistant_notes",
    "user_decision",
    "user_comment",
)

REVIEW_NOTES = {
    "S002": "別規程の対象であることは確認できるが、会計年度任用職員の支給日は対象文書から確定できないため文書不足とした。",
    "S010": "確認先は文書に明記されている。控除額自体の正否は個別確認が必要なため判断要とした。",
    "S016": "支給停止の可能性は確認できるが、停止割合は個別規程に委ねられているため文書不足とした。",
    "S018": "一括・分割の選択肢は明記されているが、最終決定は職員事情によるため判断要とした。",
    "S027": "届出期限の起算点を明確にするため、通勤経路が変わった事例へ質問文を修正した。",
    "S057": "支給開始には認定が前提となるため、質問文へ『扶養認定された場合』を追加した。",
    "S078": "期限後も受付可能だが、反映時期は個別案件によって変わるため判断要とした。",
    "S079": "FAQは不足書類の追完を示す一方、手続きマニュアルは受付不可としている。文書間の差異を問う質問へ修正した。",
    "S090": "住居手当の本人契約・家賃負担という前提が曖昧にならないよう質問文と回答要点を修正した。",
}

REVISED_SCENARIOS = {"S027", "S057", "S079", "S090"}


def existing_user_reviews(path: Path = OUTPUT_FILE) -> dict[str, tuple[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        return {
            row["scenario_id"]: (row.get("user_decision", ""), row.get("user_comment", ""))
            for row in csv.DictReader(file)
        }


def create_review_rows() -> list[dict]:
    formal_records = [
        row for row in generate_records() if row["variant_type"] == "formal"
    ]
    saved_reviews = existing_user_reviews()
    rows = []
    for record in formal_records:
        scenario_id = record["scenario_id"]
        user_decision, user_comment = saved_reviews.get(scenario_id, ("", ""))
        rows.append(
            {
                "scenario_id": scenario_id,
                "topic": record["topic"],
                "difficulty": record["difficulty"],
                "formal_question": record["question"],
                "expected_answer_type": record["expected_answer_type"],
                "expected_answer_key": record["expected_answer_key"],
                "expected_evidence": record["expected_evidence"],
                "assistant_decision": (
                    "修正済み・承認推奨"
                    if scenario_id in REVISED_SCENARIOS
                    else "承認推奨"
                ),
                "review_priority": (
                    "重点確認" if scenario_id in REVIEW_NOTES else "通常確認"
                ),
                "assistant_notes": REVIEW_NOTES.get(
                    scenario_id,
                    "根拠文書と質問・回答要点・回答分類の対応を確認した。",
                ),
                "user_decision": user_decision,
                "user_comment": user_comment,
            }
        )
    return rows


def save_review_rows(rows: list[dict], path: Path = OUTPUT_FILE) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = create_review_rows()
    save_review_rows(rows)
    print(f"レビュー対象: {len(rows)}")
    print(f"重点確認: {sum(row['review_priority'] == '重点確認' for row in rows)}")
    print(f"出力: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
