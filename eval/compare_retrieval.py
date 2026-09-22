import argparse
import csv
from pathlib import Path


METRICS = (
    "hit_at_3",
    "hit_at_5",
    "evidence_hit_at_3",
    "evidence_hit_at_5",
)


def load_results(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows or any(
        not (row.get("question_id") or row.get("question")) for row in rows
    ):
        raise ValueError(f"質問IDまたは質問文のある結果CSVが必要です: {path}")
    records = {row.get("question_id") or row["question"]: row for row in rows}
    if len(records) != len(rows):
        raise ValueError(f"質問IDまたは質問文が重複しています: {path}")
    return records


def compare_results(
    before: dict[str, dict], after: dict[str, dict]
) -> tuple[list[dict], list[dict]]:
    """同じ質問・正解条件だけを比較する。"""
    if set(before) != set(after):
        raise ValueError("前後の質問IDが一致しません")
    for question_id in before:
        for field in (
            "question",
            "expected_document_ids",
            "expected_evidence",
            "retrieval_applicable",
        ):
            if before[question_id].get(field) != after[question_id].get(field):
                raise ValueError(f"前後の評価条件が異なります: {question_id} / {field}")

    summary = []
    for metric in METRICS:
        if any(
            (before[qid].get(metric) not in ("", None))
            != (after[qid].get(metric) not in ("", None))
            for qid in before
        ):
            raise ValueError(f"前後の指標の評価対象が異なります: {metric}")
        eligible = [
            question_id
            for question_id in before
            if before[question_id].get(metric) not in ("", None)
        ]
        if not eligible:
            continue
        old_hits = sum(int(before[qid][metric]) for qid in eligible)
        new_hits = sum(int(after[qid][metric]) for qid in eligible)
        summary.append(
            {
                "metric": metric,
                "before": old_hits,
                "after": new_hits,
                "total": len(eligible),
            }
        )

    changes = []
    for question_id in before:
        old = before[question_id]
        new = after[question_id]
        if any(old.get(metric) != new.get(metric) for metric in METRICS):
            changes.append(
                {
                    "question_id": question_id,
                    "difficulty": old.get("difficulty", ""),
                    "before_document_at_3": old.get("hit_at_3", ""),
                    "after_document_at_3": new.get("hit_at_3", ""),
                    "before_document_at_5": old.get("hit_at_5", ""),
                    "after_document_at_5": new.get("hit_at_5", ""),
                    "before_evidence_at_3": old.get("evidence_hit_at_3", ""),
                    "after_evidence_at_3": new.get("evidence_hit_at_3", ""),
                    "before_evidence_at_5": old.get("evidence_hit_at_5", ""),
                    "after_evidence_at_5": new.get("evidence_hit_at_5", ""),
                }
            )
    return summary, changes


def main() -> None:
    parser = argparse.ArgumentParser(description="同じ質問セットの検索評価を比較する")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()

    summary, changes = compare_results(
        load_results(args.before), load_results(args.after)
    )
    print("指標 | 改善前 | 改善後")
    print("--- | ---: | ---:")
    for row in summary:
        print(
            f"{row['metric']} | {row['before']}/{row['total']} | {row['after']}/{row['total']}"
        )
    print("\n成否が変わった質問:")
    for row in changes:
        print(
            f"{row['question_id']} ({row['difficulty']}): "
            f"文書@3 {row['before_document_at_3']}→{row['after_document_at_3']}, "
            f"文書@5 {row['before_document_at_5']}→{row['after_document_at_5']}, "
            f"根拠@3 {row['before_evidence_at_3']}→{row['after_evidence_at_3']}, "
            f"根拠@5 {row['before_evidence_at_5']}→{row['after_evidence_at_5']}"
        )


if __name__ == "__main__":
    main()
