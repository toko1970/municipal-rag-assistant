"""人手承認済みの500問評価セットを固定し、チェックサムを保存する。"""

from datetime import date
from hashlib import sha256
from pathlib import Path
import csv
import json

from eval.generate_large_evaluation_set import OUTPUT_FILE, generate_records, save_records


REVIEW_FILE = Path("eval/evaluation_scenario_review.csv")
MANIFEST_FILE = Path("eval/evaluation_set_manifest.json")
ROW_SCHEMA_FILE = Path("design/schemas/text-evaluation-row-v1.schema.json")
VERSION = "1.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_DOCUMENTS = (
    ("DOC-001", "salary_rules", Path("docs/01_salary_rules.md")),
    ("DOC-002", "allowance_notice", Path("docs/02_allowance_notice.md")),
    ("DOC-003", "hr_faq", Path("docs/03_hr_faq.md")),
    ("DOC-004", "procedure_manual", Path("docs/04_procedure_manual.md")),
    ("DOC-005", "revision_notice", Path("docs/05_revision_notice.md")),
)


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def existing_approval_date(path: Path) -> str:
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            approved_on = value.get("approved_on")
            if isinstance(approved_on, str) and approved_on:
                return approved_on
        except (json.JSONDecodeError, OSError):
            pass
    return date.today().isoformat()


def load_reviews(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def validate_approvals(reviews: list[dict], records: list[dict]) -> None:
    if len(reviews) != 100:
        raise ValueError(f"レビュー件数が100件ではありません: {len(reviews)}")
    review_by_id = {row["scenario_id"]: row for row in reviews}
    if len(review_by_id) != 100:
        raise ValueError("レビュー表のscenario_idに重複があります")

    unapproved = {
        row["scenario_id"]: row.get("user_decision", "").strip()
        for row in reviews
        if row.get("user_decision", "").strip() != "承認"
    }
    if unapproved:
        raise ValueError(f"未承認のシナリオがあります: {unapproved}")

    formal_records = {
        row["scenario_id"]: row for row in records if row["variant_type"] == "formal"
    }
    if set(review_by_id) != set(formal_records):
        raise ValueError("レビュー表と生成データのscenario_idが一致しません")

    compared_fields = {
        "formal_question": "question",
        "expected_answer_type": "expected_answer_type",
        "expected_answer_key": "expected_answer_key",
        "expected_evidence": "expected_evidence",
    }
    for scenario_id, review in review_by_id.items():
        record = formal_records[scenario_id]
        for review_field, record_field in compared_fields.items():
            if review.get(review_field, "") != record.get(record_field, ""):
                raise ValueError(
                    f"レビュー後に正解条件が変わっています: {scenario_id} / {record_field}"
                )


def freeze_evaluation_set(
    review_path: Path = REVIEW_FILE,
    output_path: Path = OUTPUT_FILE,
    manifest_path: Path = MANIFEST_FILE,
) -> dict:
    records = generate_records()
    reviews = load_reviews(review_path)
    validate_approvals(reviews, records)

    for record in records:
        record["review_status"] = "user_approved"
    save_records(records, output_path)

    documents = []
    for document_id, document_family, relative_path in DEVELOPMENT_DOCUMENTS:
        document_path = REPOSITORY_ROOT / relative_path
        documents.append(
            {
                "document_id": document_id,
                "document_family": document_family,
                "path": str(relative_path),
                "sha256": file_hash(document_path),
            }
        )
    row_schema_path = REPOSITORY_ROOT / ROW_SCHEMA_FILE
    manifest = {
        "version": VERSION,
        "split": "development",
        "approved_on": existing_approval_date(manifest_path),
        "approved_scenarios": len(reviews),
        "questions": len(records),
        "evaluation_file": str(output_path),
        "sha256": file_hash(output_path),
        "row_schema": {
            "path": str(ROW_SCHEMA_FILE),
            "sha256": file_hash(row_schema_path),
        },
        "documents": documents,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    manifest = freeze_evaluation_set()
    print(f"評価セット: v{manifest['version']}")
    print(f"承認シナリオ: {manifest['approved_scenarios']}")
    print(f"質問数: {manifest['questions']}")
    print(f"SHA-256: {manifest['sha256']}")
    print(f"マニフェスト: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
