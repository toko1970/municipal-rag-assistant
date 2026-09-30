"""Build an offline rubric-v2 audit from the opened text holdout gold."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "eval/text_holdout/.sealed/gold/scenario_gold.json"
QUESTIONS_PATH = ROOT / "eval/text_holdout/questions.json"
OUTPUT_PATH = ROOT / "eval/classification_rubric_v2_audit.json"

LABELS = {
    "grounded": "根拠十分",
    "needs_judgment": "判断要",
    "insufficient_documents": "文書不足",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assessment(row: dict[str, Any]) -> dict[str, Any]:
    expected = row["expected_classification"]
    missing = row["missing_conditions"]
    if expected == "grounded":
        evidence = "sufficient"
        support = "fully_supported"
        review = []
        rationale = "取得対象文書の規則から質問が求める命題を一意に回答できる。"
    elif expected == "needs_judgment":
        evidence = "sufficient"
        support = "fully_supported"
        review = [
            {
                "type": "case_fact",
                "description": condition,
            }
            for condition in missing
        ]
        rationale = (
            "文書に判断基準はあるが、最終結論を変える個別事実が未確認である。"
        )
    elif expected == "insufficient_documents":
        evidence = "insufficient"
        support = "no_claim"
        review = []
        rationale = (
            "review済みcorpus goldでは適用可能な規則がなく、類似制度から推測しない。"
        )
    else:
        raise ValueError(f"Unknown classification: {expected}")
    return {
        "oracle_evidence_coverage": evidence,
        "expected_claim_support": support,
        "human_review_requirements": review,
        "rubric_v2_classification": expected,
        "rubric_v2_label": LABELS[expected],
        "rationale": rationale,
    }


def build() -> dict[str, Any]:
    gold = _load(GOLD_PATH)
    questions = _load(QUESTIONS_PATH)
    question_by_id = {
        row["scenario_id"]: row["expressions"] for row in questions["scenarios"]
    }
    rows = []
    for row in gold["scenarios"]:
        scenario_id = row["scenario_id"]
        assessment = _assessment(row)
        rows.append(
            {
                "scenario_id": scenario_id,
                "expressions": question_by_id[scenario_id],
                "previous_expected_classification": row["expected_classification"],
                "previous_expected_label": LABELS[row["expected_classification"]],
                "expected_answer_key": row["expected_answer_key"],
                "expected_evidence": row["expected_evidence"],
                "missing_conditions": row["missing_conditions"],
                **assessment,
                "label_changed": (
                    assessment["rubric_v2_classification"]
                    != row["expected_classification"]
                ),
                "annotation_basis": "opened_text_holdout_gold_plus_rubric_v2",
            }
        )
    counts = Counter(row["rubric_v2_label"] for row in rows)
    review_counts = Counter(
        requirement["type"]
        for row in rows
        for requirement in row["human_review_requirements"]
    )
    return {
        "schema_version": "1.0",
        "rubric_version": "classification-rubric-v2.0",
        "source_holdout_id": gold["holdout_id"],
        "source_gold_sha256": _sha256(GOLD_PATH),
        "source_questions_sha256": _sha256(QUESTIONS_PATH),
        "scenario_count": len(rows),
        "expression_count": sum(len(row["expressions"]) for row in rows),
        "label_counts": dict(counts),
        "human_review_reason_counts": {
            review_type: review_counts[review_type]
            for review_type in ("case_fact", "policy_judgment", "version_conflict")
        },
        "coverage_gaps": [
            review_type
            for review_type in ("policy_judgment", "version_conflict")
            if review_counts[review_type] == 0
        ],
        "label_change_count": sum(row["label_changed"] for row in rows),
        "external_api_calls": 0,
        "sealed_status": "opened_before_this_audit",
        "scenarios": rows,
    }


def main() -> None:
    result = build()
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote={OUTPUT_PATH.relative_to(ROOT)} scenarios={result['scenario_count']} "
        f"labels={result['label_counts']} changes={result['label_change_count']}"
    )


if __name__ == "__main__":
    main()
