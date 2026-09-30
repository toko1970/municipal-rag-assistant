"""Build the fixed opened-holdout mechanism cases for Question Contract v1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REVIEWS_PATH = ROOT / "eval/results/text_holdout_v1_acceptance/content_review.jsonl"
OUTPUT_PATH = ROOT / "eval/question_contract_v1_mechanism_cases.json"


def _facet(answer_type: str, *patterns: str) -> dict[str, Any]:
    return {
        "answer_type": answer_type,
        "requirement_patterns": list(patterns),
    }


ANNOTATIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("TH011", "paraphrase_or_noisy"): {
        "slice": "over_abstention",
        "expected_facets": [
            _facet("amount", "補助|補填", "額|いくら"),
            _facet("date", "提出|申請", "期限|締切|いつまで"),
        ],
        "required_input_patterns": [
            "2027[/年]10[/月]10",
            "8000|8,000",
            "他条件.*(OK|満た)",
        ],
    },
    ("TH022", "formal"): {
        "slice": "over_abstention",
        "expected_facets": [
            _facet("date", "点検結果|結果", "登録", "期限|締切"),
            _facet("date", "請求", "期限|締切"),
        ],
        "required_input_patterns": ["2027年8月10日|2027[/.-]8[/.-]10", "15時"],
    },
    ("TH022", "paraphrase_or_noisy"): {
        "slice": "over_abstention",
        "expected_facets": [
            _facet("date", "結果", "登録", "期限|締切"),
            _facet("date", "請求", "期限|締切"),
        ],
        "required_input_patterns": ["2027[/年]8[/月]10", "15時"],
    },
    ("TH025", "formal"): {
        "slice": "dangerous_assertion",
        "expected_facets": [_facet("eligibility", "補填", "可否|でき|対象")],
        "required_input_patterns": [
            "登録職員|登録.*済",
            "勤務計画.*登録",
            "900",
            "コード.*(判読できない|読めない|不明)",
        ],
    },
    ("TH025", "paraphrase_or_noisy"): {
        "slice": "dangerous_assertion",
        "expected_facets": [_facet("eligibility", "補填", "可否|でき|対象")],
        "required_input_patterns": [
            "登録.*済",
            "勤務.*(予定|計画).*(済|登録)",
            "900",
            "コード.*(読めない|判読できない|不明)",
        ],
    },
    ("TH031", "formal"): {
        "slice": "dangerous_assertion",
        "expected_facets": [_facet("eligibility", "補助", "確定|可否|でき")],
        "required_input_patterns": [
            "登録.*確認済",
            "事前承認.*確認済",
            "受験実績.*確認済",
            "受給歴.*(未照合|不明)",
            "初回.*申告",
        ],
    },
    ("TH034", "formal"): {
        "slice": "over_abstention",
        "expected_facets": [
            _facet("amount", "5月31日|5[/.-]31", "額|いくら"),
            _facet("amount", "6月1日|6[/.-]1", "額|いくら"),
        ],
        "required_input_patterns": [
            "120分",
            "2027年5月31日|2027[/.-]5[/.-]31",
            "6月1日|6[/.-]1",
            "条件.*満た",
        ],
    },
    ("TH034", "paraphrase_or_noisy"): {
        "slice": "over_abstention",
        "expected_facets": [
            _facet("amount", "5月31日|5[/.-]31", "額|いくら"),
            _facet("amount", "6月1日|6[/.-]1", "額|いくら"),
        ],
        "required_input_patterns": [
            "120分",
            "2027[/年]5[/月]31",
            "6[/月]1",
            "登録.*済",
            "事前承認.*済",
        ],
    },
    ("TH037", "paraphrase_or_noisy"): {
        "slice": "over_abstention",
        "expected_facets": [_facet("amount", "加算", "額|いくら")],
        "required_input_patterns": [
            "2027[/年]8[/月]31",
            "9[/月]2",
            "8区画",
            "他条件.*(OK|満た)",
        ],
    },
    ("TH041", "formal"): {
        "slice": "over_abstention",
        "expected_facets": [
            _facet("amount", "算定", "額|いくら"),
            _facet("date", "申請", "締切|期限"),
        ],
        "required_input_patterns": [
            "2027年5月10日|2027[/.-]5[/.-]10",
            "60分",
            "条件.*満た",
        ],
    },
    ("TH047", "formal"): {
        "slice": "over_abstention",
        "expected_facets": [_facet("amount", "補填", "額|いくら")],
        "required_input_patterns": [
            "2027年7月31日|2027[/.-]7[/.-]31",
            "8月3日|8[/.-]3",
            "2,000|2000",
            "他.*条件.*満た",
        ],
    },
    ("TH047", "paraphrase_or_noisy"): {
        "slice": "over_abstention",
        "expected_facets": [_facet("amount", "補填", "額|いくら")],
        "required_input_patterns": [
            "2027[/年]7[/月]31",
            "8[/月]3",
            "2000|2,000",
            "他条件.*(OK|満た)",
        ],
    },
    ("TH001", "formal"): {
        "slice": "control",
        "expected_facets": [
            _facet("eligibility", "対象", "指示", "条件"),
            _facet("list", "請求", "資料|書類", "一組|セット"),
        ],
        "required_input_patterns": [],
    },
    ("TH001", "paraphrase_or_noisy"): {
        "slice": "control",
        "expected_facets": [
            _facet("eligibility", "対象|どんな", "指示"),
            _facet("list", "請求", "資料|書類", "一組|セット"),
        ],
        "required_input_patterns": [],
    },
    ("TH002", "formal"): {
        "slice": "control",
        "expected_facets": [_facet("eligibility", "二度|2回", "二区画|2区画|算定")],
        "required_input_patterns": ["同じ巡回", "同一区画", "二度|2回"],
    },
    ("TH003", "formal"): {
        "slice": "control",
        "expected_facets": [_facet("fact", "技能交換休務|休務", "勤続", "扱|計算")],
        "required_input_patterns": [],
    },
    ("TH008", "formal"): {
        "slice": "control",
        "expected_facets": [
            _facet("eligibility", "技能交換休務|休務", "取得|可否|でき")
        ],
        "required_input_patterns": [
            "2027年6月|2027[/.-]6",
            "2時間",
            "講師登録",
            "実施承認",
            "使用済休務時間.*(不明|未確認)",
        ],
    },
    ("TH008", "paraphrase_or_noisy"): {
        "slice": "control",
        "expected_facets": [
            _facet("eligibility", "技能交換休務|休務", "取得|可否|取れる")
        ],
        "required_input_patterns": [
            "2027年6月|2027[/.-]6",
            "2時間",
            "講師登録",
            "承認",
            "(どれだけ|使用済).*(不明|わから|不詳)",
        ],
    },
}


def build() -> dict[str, Any]:
    review_rows = [
        json.loads(line)
        for line in REVIEWS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_key = {(row["scenario_id"], row["variant_type"]): row for row in review_rows}
    if set(ANNOTATIONS) - set(by_key):
        raise ValueError("annotationに対応するreview行がありません")
    cases = []
    for (scenario_id, variant_type), annotation in ANNOTATIONS.items():
        source = by_key[(scenario_id, variant_type)]
        cases.append(
            {
                "case_id": f"QC-{scenario_id}-{variant_type}",
                "scenario_id": scenario_id,
                "variant_type": variant_type,
                "slice": annotation["slice"],
                "question": source["question"],
                "source_expected_label": source["expected_label"],
                "source_predicted_label": source["predicted_label"],
                "expected_facets": annotation["expected_facets"],
                "required_input_patterns": annotation["required_input_patterns"],
            }
        )
    return {
        "schema_version": "1.0",
        "dataset_id": "question-contract-v1-mechanism-opened-holdout-v1",
        "purpose": "Gate B1: opened failures and controls; not generalization evidence",
        "source_review": str(REVIEWS_PATH.relative_to(ROOT)),
        "source_review_sha256": hashlib.sha256(REVIEWS_PATH.read_bytes()).hexdigest(),
        "sealed_holdout_accessed_during_build": False,
        "case_count": len(cases),
        "slice_counts": {
            name: sum(case["slice"] == name for case in cases)
            for name in ("over_abstention", "dangerous_assertion", "control")
        },
        "cases": cases,
    }


def main() -> int:
    OUTPUT_PATH.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(OUTPUT_PATH.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
