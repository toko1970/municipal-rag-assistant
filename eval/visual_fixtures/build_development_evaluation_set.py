"""Build the deterministic 30-scenario visual development evaluation set."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from eval.validate_visual_fixture import sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPOSITORY_ROOT / "eval/visual_fixtures/development_evaluation_set.json"
MANIFEST_PATH = REPOSITORY_ROOT / "eval/visual_fixtures/manifests/development_evaluation_manifest.json"
SCHEMA_PATH = REPOSITORY_ROOT / "design/schemas/visual-evaluation-set-v1.schema.json"
FIXTURE_MANIFEST_PATH = (
    REPOSITORY_ROOT / "eval/visual_fixtures/manifests/development_manifest.json"
)


def evidence(fixture_id: str, *element_refs: str) -> list[dict[str, str]]:
    return [
        {"fixture_id": fixture_id, "element_ref": element_ref}
        for element_ref in element_refs
    ]


def scenario(
    question: str,
    fixture_id: str,
    visual_type: str,
    difficulty: str,
    classification: str,
    answer: str,
    evidence_refs: list[dict[str, str]],
    missing_conditions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "question": question,
        "fixture_ids": [fixture_id],
        "visual_type": visual_type,
        "difficulty": difficulty,
        "expected_classification": classification,
        "expected_corpus_answerability": classification != "insufficient_documents",
        "expected_answer_key": answer,
        "required_evidence": evidence_refs,
        "missing_conditions": missing_conditions or [],
    }


def scenarios() -> list[dict[str, Any]]:
    rows = [
        scenario(
            "通勤手当の申請書を受領した後、最初に何を確認しますか？",
            "flowchart_dev_001",
            "process_flow",
            "direct",
            "grounded",
            "記載内容と添付書類を確認する。",
            evidence("flowchart_dev_001", "node:start", "node:check"),
        ),
        scenario(
            "通勤手当申請に不備がなかった場合、確認後から処理完了までの流れを教えてください。",
            "flowchart_dev_001",
            "process_flow",
            "multi_element",
            "grounded",
            "不備なしの分岐から給与システムへ登録し、処理完了となる。",
            evidence(
                "flowchart_dev_001",
                "node:decision",
                "edge:decision->register",
                "node:register",
                "node:end",
            ),
        ),
        scenario(
            "申請にモレがあって差し戻した後は、どの工程へ戻りますか？",
            "flowchart_dev_001",
            "process_flow",
            "paraphrase_or_typo",
            "grounded",
            "再提出後、記載内容・添付書類の確認工程へ戻る。",
            evidence(
                "flowchart_dev_001",
                "node:return",
                "edge:return->check",
                "node:check",
            ),
        ),
        scenario(
            "添付書類の記載が読みにくい申請を、そのまま給与システムへ登録してよいですか？",
            "flowchart_dev_001",
            "process_flow",
            "boundary_or_revision",
            "needs_judgment",
            "図は不備の有無で経路を分けるが、読みにくさを不備とする基準は示していないため確認が必要。",
            evidence("flowchart_dev_001", "node:decision", "edge:decision->register"),
            ["読みにくい記載を不備と扱う運用基準"],
        ),
        scenario(
            "通勤手当申請に必要な添付書類をすべて教えてください。",
            "flowchart_dev_001",
            "process_flow",
            "paraphrase_or_typo",
            "insufficient_documents",
            "図には添付書類を確認することだけがあり、書類名の一覧は記載されていない。",
            [],
        ),
        scenario(
            "住居手当の必要書類が揃っていない場合、次に何をしますか？",
            "flowchart_dev_002",
            "decision_flow",
            "direct",
            "grounded",
            "追加提出を依頼する。",
            evidence(
                "flowchart_dev_002",
                "node:documents",
                "edge:documents->request_documents",
                "node:request_documents",
            ),
        ),
        scenario(
            "対象職員で、必要書類が揃い、支給要件も満たす場合の判定経路を教えてください。",
            "flowchart_dev_002",
            "decision_flow",
            "multi_element",
            "grounded",
            "3つの判断をすべて「はい」で進み、支給対象となる。",
            evidence(
                "flowchart_dev_002",
                "edge:employee->documents",
                "edge:documents->requirements",
                "edge:requirements->eligible",
                "node:eligible",
            ),
        ),
        scenario(
            "住居手当の対象スタッフじゃないときの結論は？",
            "flowchart_dev_002",
            "decision_flow",
            "paraphrase_or_typo",
            "grounded",
            "支給対象外となる。",
            evidence(
                "flowchart_dev_002",
                "node:employee",
                "edge:employee->not_eligible",
                "node:not_eligible",
            ),
        ),
        scenario(
            "この職員の住居手当申請は支給対象になりますか？",
            "flowchart_dev_002",
            "decision_flow",
            "boundary_or_revision",
            "needs_judgment",
            "対象職員、必要書類、支給要件の3条件が不明なため、個別の支給可否は判断できない。",
            evidence(
                "flowchart_dev_002",
                "node:employee",
                "node:documents",
                "node:requirements",
            ),
            ["対象職員か", "必要書類が揃っているか", "支給要件を満たすか"],
        ),
        scenario(
            "住居手当の必要書類の名称を一覧で教えてください。",
            "flowchart_dev_002",
            "decision_flow",
            "paraphrase_or_typo",
            "insufficient_documents",
            "図には必要書類の名称が記載されていない。",
            [],
        ),
        scenario(
            "扶養状況の異動後、職員はいつまでに届出書を提出しますか？",
            "timeline_dev_001",
            "timeline",
            "direct",
            "grounded",
            "異動日の翌日から10日以内に提出する。",
            evidence("timeline_dev_001", "event:change_known", "event:submit"),
        ),
        scenario(
            "扶養手当の届出を受領した後、給与担当者は何営業日以内に確認しますか？",
            "timeline_dev_001",
            "timeline",
            "direct",
            "grounded",
            "受領後2営業日以内に確認する。",
            evidence("timeline_dev_001", "event:review"),
        ),
        scenario(
            "扶養状況の変更確認から手当額の反映まで、処理順に説明してください。",
            "timeline_dev_001",
            "timeline",
            "multi_element",
            "grounded",
            "変更確認、10日以内の提出、2営業日以内の確認、当月締切までの登録、翌月給与への反映の順。",
            evidence(
                "timeline_dev_001",
                "event:change_known",
                "event:submit",
                "event:review",
                "event:register",
                "event:payment",
            ),
        ),
        scenario(
            "当月給与の締切日を過ぎて受領した届出を、当月分へ例外登録してよいですか？",
            "timeline_dev_001",
            "timeline",
            "boundary_or_revision",
            "needs_judgment",
            "図は締切日までの登録を示すが、期限後の例外処理は示していないため個別確認が必要。",
            evidence("timeline_dev_001", "event:register", "event:payment"),
            ["実際の受領日", "当月給与の締切日", "期限後登録の例外運用"],
        ),
        scenario(
            "今月の給与システム締切日は何月何日ですか？",
            "timeline_dev_001",
            "timeline",
            "boundary_or_revision",
            "insufficient_documents",
            "図には『当月給与の締切日まで』とだけあり、具体的な年月日は記載されていない。",
            [],
        ),
        scenario(
            "月15日以上通勤する常勤職員の通勤手当月額はいくらですか？",
            "table_dev_001",
            "table",
            "direct",
            "grounded",
            "12,000円で、表では上限額とされている。",
            evidence("table_dev_001", "cell:r1c0", "cell:r1c1", "cell:r1c2", "cell:r1c3"),
        ),
        scenario(
            "月1〜7日通勤する短時間職員の通勤手当はいくらですか？",
            "table_dev_001",
            "table",
            "direct",
            "grounded",
            "4,000円。",
            evidence("table_dev_001", "cell:r3c0", "cell:r3c1", "cell:r3c2"),
        ),
        scenario(
            "常勤職員の通勤日数が月8〜14日の場合と15日以上の場合で、月額はいくら違いますか？",
            "table_dev_001",
            "table",
            "multi_element",
            "grounded",
            "8〜14日は8,000円、15日以上は12,000円で、差は4,000円。",
            evidence(
                "table_dev_001",
                "cell:r1c0",
                "cell:r1c1",
                "cell:r1c2",
                "cell:r2c1",
                "cell:r2c2",
            ),
        ),
        scenario(
            "月10日通勤した職員の区分が分からない場合、通勤手当額を確定できますか？",
            "table_dev_001",
            "table",
            "boundary_or_revision",
            "needs_judgment",
            "常勤職員なら8,000円の行に該当するが、職員区分が不明なため確定できない。",
            evidence("table_dev_001", "cell:r1c0", "cell:r2c1", "cell:r2c2"),
            ["職員区分"],
        ),
        scenario(
            "月8日以上通勤する短時間職員の通勤手当額を教えてください。",
            "table_dev_001",
            "table",
            "boundary_or_revision",
            "insufficient_documents",
            "表には短時間職員の月1〜7日だけがあり、月8日以上の金額は記載されていない。",
            [],
        ),
        scenario(
            "扶養手当認定届の記入例では、添付書類として何が記載されていますか？",
            "form_dev_001",
            "form",
            "direct",
            "grounded",
            "住民票の写し。",
            evidence("form_dev_001", "field:attachment"),
        ),
        scenario(
            "扶養手当認定届の記入例にある入力項目をすべて挙げてください。",
            "form_dev_001",
            "form",
            "multi_element",
            "grounded",
            "職員番号、氏名、異動年月日、扶養親族氏名、続柄、異動理由、添付書類。",
            evidence(
                "form_dev_001",
                "field:employee_id",
                "field:employee_name",
                "field:effective_date",
                "field:dependent_name",
                "field:relationship",
                "field:change_reason",
                "field:attachment",
            ),
        ),
        scenario(
            "記入例の『いどう年月日』と『いどう理由』には何と書かれていますか？",
            "form_dev_001",
            "form",
            "paraphrase_or_typo",
            "grounded",
            "異動年月日は2026年4月1日、異動理由は出生。",
            evidence("form_dev_001", "field:effective_date", "field:change_reason"),
        ),
        scenario(
            "転居を理由とする届出でも、添付書類はこの例と同じ住民票の写しだけで足りますか？",
            "form_dev_001",
            "form",
            "boundary_or_revision",
            "needs_judgment",
            "記入例は出生の例であり、転居時の必要書類は個別に確認する必要がある。",
            evidence("form_dev_001", "field:change_reason", "field:attachment"),
            ["転居時に適用される添付書類の規定", "届出対象者の個別事情"],
        ),
        scenario(
            "この届出の承認者はどの欄に署名しますか？",
            "form_dev_001",
            "form",
            "direct",
            "insufficient_documents",
            "記入例には承認者の署名欄が記載されていない。",
            [],
        ),
        scenario(
            "改定後の住居手当はいくらで、条件は何ですか？",
            "table_dev_002",
            "revision_comparison",
            "direct",
            "grounded",
            "12,000円で、条件は要件B。",
            evidence("table_dev_002", "cell:r2c0", "cell:r2c3", "cell:r2c4"),
        ),
        scenario(
            "通勤手当について、改定前後の金額と条件を比較してください。",
            "table_dev_002",
            "revision_comparison",
            "multi_element",
            "grounded",
            "改定前は8,000円・月8日以上、改定後は9,000円・月6日以上。",
            evidence(
                "table_dev_002",
                "cell:r3c0",
                "cell:r3c1",
                "cell:r3c2",
                "cell:r3c3",
                "cell:r3c4",
            ),
        ),
        scenario(
            "新しい手当金額と条件はいつから適用されますか？",
            "table_dev_002",
            "revision_comparison",
            "boundary_or_revision",
            "grounded",
            "2026年4月1日から。",
            evidence("table_dev_002", "cell:r4c0", "cell:r4c1"),
        ),
        scenario(
            "2026年4月1日をまたぐ期間の住居手当申請には、改定前後のどちらを適用しますか？",
            "table_dev_002",
            "revision_comparison",
            "boundary_or_revision",
            "needs_judgment",
            "施行日は確認できるが、期間をまたぐ申請の適用基準日が不明なため個別確認が必要。",
            evidence(
                "table_dev_002",
                "cell:r2c1",
                "cell:r2c3",
                "cell:r4c1",
            ),
            ["申請の適用基準日", "対象期間", "経過措置の有無"],
        ),
        scenario(
            "住居手当と通勤手当が改定された理由を教えてください。",
            "table_dev_002",
            "revision_comparison",
            "multi_element",
            "insufficient_documents",
            "比較表には改定理由が記載されていない。",
            [],
        ),
    ]
    for index, row in enumerate(rows, start=1):
        row["scenario_id"] = f"VD{index:03d}"
    return rows


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    evaluation_set = {
        "schema_version": "1.0",
        "dataset_version": "visual-development-v1.0",
        "split": "development",
        "review_status": "user_approved",
        "scenario_count": 30,
        "scenarios": scenarios(),
    }
    write_json(OUTPUT_PATH, evaluation_set)
    classification_counts = Counter(
        row["expected_classification"] for row in evaluation_set["scenarios"]
    )
    visual_type_counts = Counter(
        row["visual_type"] for row in evaluation_set["scenarios"]
    )
    difficulty_counts = Counter(
        row["difficulty"] for row in evaluation_set["scenarios"]
    )
    manifest = {
        "manifest_version": "1.0",
        "dataset_version": evaluation_set["dataset_version"],
        "split": "development",
        "review_status": evaluation_set["review_status"],
        "schema": {
            "path": str(SCHEMA_PATH.relative_to(REPOSITORY_ROOT)),
            "sha256": sha256(SCHEMA_PATH),
        },
        "fixture_manifest": {
            "path": str(FIXTURE_MANIFEST_PATH.relative_to(REPOSITORY_ROOT)),
            "sha256": sha256(FIXTURE_MANIFEST_PATH),
        },
        "evaluation_set": {
            "path": str(OUTPUT_PATH.relative_to(REPOSITORY_ROOT)),
            "sha256": sha256(OUTPUT_PATH),
            "scenario_count": evaluation_set["scenario_count"],
        },
        "classification_counts": dict(classification_counts),
        "visual_type_counts": dict(visual_type_counts),
        "difficulty_counts": dict(difficulty_counts),
    }
    write_json(MANIFEST_PATH, manifest)
    print(f"wrote scenarios={len(evaluation_set['scenarios'])} path={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
