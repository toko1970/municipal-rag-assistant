"""500問評価セットの構造と根拠参照を検証する。"""

from collections import Counter, defaultdict
from pathlib import Path
import csv

from eval.evaluate_retrieval import expected_document_ids, expected_evidence
from src.chunking import split_documents
from src.document_loader import load_markdown_documents


EVALUATION_FILE = Path("eval/evaluation_questions_500.csv")
EXPECTED_VARIANTS = {"formal", "staff_consultation", "concise", "colloquial", "noisy"}
ANSWER_TYPES = {"根拠十分", "判断要", "文書不足"}


def available_evidence() -> set[tuple[str, str]]:
    evidence = set()
    for chunk in split_documents(load_markdown_documents()):
        heading = " > ".join(
            str(chunk.metadata[key])
            for key in ("見出し1", "見出し2", "見出し3")
            if chunk.metadata.get(key)
        )
        evidence.add((str(chunk.metadata.get("document_id", "")), heading))
    return evidence


def load_rows(path: Path = EVALUATION_FILE) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def validate_rows(rows: list[dict], evidence_catalog=None) -> dict:
    errors = []
    if len(rows) != 500:
        errors.append(f"質問数が500件ではありません: {len(rows)}")

    expected_question_ids = [f"Q{number:03d}" for number in range(1, 501)]
    actual_question_ids = [row.get("question_id", "") for row in rows]
    if actual_question_ids != expected_question_ids:
        errors.append("question_idがQ001からQ500の連番ではありません")

    for field in ("question_id", "scenario_id", "question"):
        values = [row.get(field, "") for row in rows]
        if "" in values:
            errors.append(f"空欄があります: {field}")
        if len(values) != len(set(values)) and field != "scenario_id":
            errors.append(f"重複があります: {field}")

    by_scenario = defaultdict(list)
    for row in rows:
        by_scenario[row.get("scenario_id", "")].append(row)
        if row.get("expected_answer_type") not in ANSWER_TYPES:
            errors.append(f"回答分類が不正です: {row.get('question_id')}")
        if not row.get("expected_answer_key", "").strip():
            errors.append(f"回答要点が空です: {row.get('question_id')}")
        if row.get("review_status") != "assistant_draft":
            errors.append(f"レビュー状態が不正です: {row.get('question_id')}")

        try:
            document_ids = expected_document_ids(row)
            required_evidence = expected_evidence(row, document_ids)
        except ValueError as error:
            errors.append(str(error))
            continue

        if row.get("expected_answer_type") == "文書不足":
            if document_ids or required_evidence:
                errors.append(f"文書不足に正解根拠があります: {row.get('question_id')}")
        elif not required_evidence:
            errors.append(f"回答可能な質問に正解根拠がありません: {row.get('question_id')}")

        if evidence_catalog is not None:
            missing = set(required_evidence) - evidence_catalog
            if missing:
                errors.append(f"存在しない根拠です: {row.get('question_id')} / {sorted(missing)}")

    if len(by_scenario) != 100:
        errors.append(f"シナリオ数が100件ではありません: {len(by_scenario)}")
    expected_scenario_ids = {f"S{number:03d}" for number in range(1, 101)}
    if set(by_scenario) != expected_scenario_ids:
        errors.append("scenario_idがS001からS100の範囲ではありません")
    for scenario_id, scenario_rows in by_scenario.items():
        variants = {row.get("variant_type", "") for row in scenario_rows}
        if len(scenario_rows) != 5 or variants != EXPECTED_VARIANTS:
            errors.append(f"表現違いが5種類ではありません: {scenario_id} / {sorted(variants)}")
        stable_fields = (
            "expected_document_ids",
            "expected_heading",
            "expected_answer_type",
            "expected_evidence",
            "expected_answer_key",
        )
        for field in stable_fields:
            if len({row.get(field, "") for row in scenario_rows}) != 1:
                errors.append(f"シナリオ内で正解条件が不一致です: {scenario_id} / {field}")

    if errors:
        raise ValueError("\n".join(errors))

    return {
        "questions": len(rows),
        "scenarios": len(by_scenario),
        "answer_types": Counter(row["expected_answer_type"] for row in rows),
        "difficulties": Counter(row["difficulty"] for row in rows),
        "topics": Counter(row["topic"] for row in rows),
    }


def main() -> None:
    summary = validate_rows(load_rows(), available_evidence())
    print(f"質問数: {summary['questions']}")
    print(f"シナリオ数: {summary['scenarios']}")
    print(f"回答分類: {dict(summary['answer_types'])}")
    print(f"難易度: {dict(summary['difficulties'])}")
    print(f"分野: {dict(summary['topics'])}")


if __name__ == "__main__":
    main()
