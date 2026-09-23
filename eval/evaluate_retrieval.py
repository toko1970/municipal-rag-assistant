from pathlib import Path
import argparse
import csv

from src.retriever import retrieve_documents_with_score


EVALUATION_FILE = Path("eval/evaluation_questions_practical.csv")
TOP_K = 5
RESULT_FIELDS = [
    "question_id",
    "question",
    "expected_document_ids",
    "expected_heading",
    "expected_evidence",
    "expected_answer_type",
    "difficulty",
    "top_k",
    "retrieved_document_ids",
    "retrieved_headings",
    "retrieval_applicable",
    "document_recall_at_1",
    "document_recall_at_3",
    "document_recall_at_5",
    "evidence_recall_at_1",
    "evidence_recall_at_3",
    "evidence_recall_at_5",
    "evidence_hit_at_1",
    "evidence_hit_at_3",
    "evidence_hit_at_5",
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
]


def load_evaluation_questions(file_path: Path) -> list[dict]:
    """
    評価用CSVを読み込む。
    """
    with file_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def expected_document_ids(row: dict) -> list[str]:
    """新しい複数文書形式と従来の単一文書形式を読み取る。"""
    value = row.get("expected_document_ids") or row.get("expected_document_id", "")
    ids = [item.strip() for item in value.split("|") if item.strip()]
    if len(ids) != len(set(ids)):
        raise ValueError(f"正解文書IDが重複しています: {row.get('question', '')}")
    if not ids and row.get("expected_answer_type") != "文書不足":
        raise ValueError(f"正解文書IDがありません: {row.get('question', '')}")
    return ids


def expected_evidence(row: dict, required_ids: list[str]) -> list[tuple[str, str]]:
    """根拠の文書IDと見出しパスを読み取る。未指定の旧セットは文書単位のみ評価する。"""
    value = row.get("expected_evidence", "")
    if not value:
        return []
    evidence = []
    for item in value.split("|"):
        document_id, separator, heading = item.partition("::")
        if not separator or not document_id.strip() or not heading.strip():
            raise ValueError(f"根拠の形式が不正です: {row.get('question', '')}")
        evidence.append((document_id.strip(), heading.strip()))
    if not required_ids or {doc_id for doc_id, _ in evidence} != set(required_ids):
        raise ValueError(f"根拠と正解文書IDが一致しません: {row.get('question', '')}")
    return evidence


def evaluate_retrieval(questions: list[dict], retrieve_fn=None) -> list[dict]:
    """
    正解文書の取得率と、必要文書をすべて取得できた割合を評価する。
    文書に答えがない質問は検索失敗として数えない。
    """
    if not questions:
        raise ValueError("評価質問がありません")
    if retrieve_fn is None:
        retrieve_fn = retrieve_documents_with_score

    records = []

    for row in questions:
        question = row["question"]
        required_ids = expected_document_ids(row)
        required_evidence = expected_evidence(row, required_ids)

        results = retrieve_fn(
            query=question,
            top_k=TOP_K,
        )

        retrieved_document_ids = [
            doc.metadata.get("document_id", "") for doc, _score in results
        ]
        retrieved_headings = [
            " > ".join(
                str(doc.metadata[key])
                for key in ("見出し1", "見出し2", "見出し3")
                if doc.metadata.get(key)
            )
            for doc, _score in results
        ]

        record = {
            "question_id": row.get("question_id", ""),
            "question": question,
            "expected_document_ids": "|".join(required_ids),
            "expected_heading": row.get("expected_heading", ""),
            "expected_evidence": row.get("expected_evidence", ""),
            "expected_answer_type": row.get("expected_answer_type", ""),
            "difficulty": row.get("difficulty", ""),
            "top_k": TOP_K,
            "retrieved_document_ids": "|".join(retrieved_document_ids),
            "retrieved_headings": "|".join(retrieved_headings),
            "retrieval_applicable": int(bool(required_ids)),
        }
        for k in (1, 3, 5):
            found_ids = set(retrieved_document_ids[:k])
            record[f"document_recall_at_{k}"] = (
                len(found_ids.intersection(required_ids)) / len(required_ids)
                if required_ids
                else ""
            )
            record[f"hit_at_{k}"] = (
                int(set(required_ids).issubset(found_ids)) if required_ids else ""
            )
            found_evidence = set(
                zip(retrieved_document_ids[:k], retrieved_headings[:k])
            )
            record[f"evidence_recall_at_{k}"] = (
                len(found_evidence.intersection(required_evidence))
                / len(required_evidence)
                if required_evidence
                else ""
            )
            record[f"evidence_hit_at_{k}"] = (
                int(set(required_evidence).issubset(found_evidence))
                if required_evidence
                else ""
            )
        records.append(record)

        print("=" * 80)
        print(f"質問: {question}")
        print(f"正解文書: {required_ids or 'なし（検索評価の対象外）'}")
        print(f"検索結果: {retrieved_document_ids}")
        if required_ids:
            for k in (1, 3, 5):
                print(f"全必要文書 Hit@{k}: {bool(record[f'hit_at_{k}'])}")

    print("\n" + "=" * 80)
    print("検索性能評価結果")
    print("=" * 80)
    applicable = [record for record in records if record["retrieval_applicable"]]
    evidence_applicable = [record for record in records if record["expected_evidence"]]
    print(
        f"質問数: {len(records)}（検索評価対象: {len(applicable)}、文書不足: {len(records) - len(applicable)}）"
    )
    for k in (1, 3, 5):
        if applicable:
            recall = sum(
                record[f"document_recall_at_{k}"] for record in applicable
            ) / len(applicable)
            hits = sum(record[f"hit_at_{k}"] for record in applicable)
            print(f"文書Recall@{k}: {recall:.2f}")
            print(
                f"全必要文書Hit@{k}: {hits / len(applicable):.2f} ({hits}/{len(applicable)})"
            )
        if evidence_applicable:
            evidence_recall = sum(
                record[f"evidence_recall_at_{k}"] for record in evidence_applicable
            ) / len(evidence_applicable)
            evidence_hits = sum(
                record[f"evidence_hit_at_{k}"] for record in evidence_applicable
            )
            print(f"根拠見出しRecall@{k}: {evidence_recall:.2f}")
            print(
                f"全根拠見出しHit@{k}: {evidence_hits / len(evidence_applicable):.2f} ({evidence_hits}/{len(evidence_applicable)})"
            )

    return records


def save_results(records: list[dict], output_path: Path) -> None:
    """質問ごとの検索結果をCSVに保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description="検索性能を質問ごとに評価する")
    parser.add_argument("--input", type=Path, default=EVALUATION_FILE)
    parser.add_argument("--output", type=Path, help="質問ごとの結果を保存するCSV")
    parser.add_argument(
        "--method",
        choices=("vector", "hybrid", "contextual"),
        default="vector",
    )
    args = parser.parse_args()

    questions = load_evaluation_questions(args.input)
    if args.method == "hybrid":
        from eval.hybrid_retriever import retrieve_documents_with_score as retrieve_fn
    elif args.method == "contextual":
        from eval.contextual_retriever import (
            retrieve_documents_with_score as retrieve_fn,
        )
    else:
        retrieve_fn = retrieve_documents_with_score
    records = evaluate_retrieval(questions, retrieve_fn=retrieve_fn)
    if args.output:
        save_results(records, args.output)
        print(f"結果CSV: {args.output}")


if __name__ == "__main__":
    main()
