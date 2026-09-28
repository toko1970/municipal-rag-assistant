"""Combine text and visual retrieved-evidence regression into one failure ledger."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def _read_jsonl(path: Path, id_field: str) -> dict[str, dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line]
    result = {record[id_field]: record for record in records}
    if len(result) != len(records):
        raise ValueError(f"IDが重複しています: {path}")
    return result


def _old_label(factors: dict[str, bool]) -> str:
    if (
        factors["version_conflict"]
        or factors["requires_case_facts"]
        or factors["requires_policy_judgment"]
    ):
        return "判断要"
    if not factors["retrieval_sufficient"] or not factors["answer_fully_supported"]:
        return "文書不足"
    return "根拠十分"


def _annotations(review: dict[str, Any], modality: str) -> dict[str, str]:
    result = {}
    for cause, ids in review[f"{modality}_failures"].items():
        for item_id in ids:
            if item_id in result:
                raise ValueError(f"主原因が重複しています: {item_id}")
            result[item_id] = cause
    return result


def analyze(
    text: dict[str, dict[str, Any]],
    visual: dict[str, dict[str, Any]],
    top_k: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    if len(text) != review["reviewed_text_questions"]:
        raise ValueError("text review件数がrunと一致しません")
    if len(visual) != review["reviewed_visual_questions"]:
        raise ValueError("visual review件数がrunと一致しません")

    top_k_by_id = {record["question_id"]: record for record in top_k["records"]}
    text_causes = _annotations(review, "text")
    visual_causes = _annotations(review, "visual")
    if not set(text_causes) <= set(text) or not set(visual_causes) <= set(visual):
        raise ValueError("reviewにrun外のIDがあります")

    ledger = []
    for question_id, record in text.items():
        retrieval = top_k_by_id[question_id]
        retrieval_ok = (
            bool(retrieval["metrics"]["8"]["evidence_hit"])
            if retrieval["retrieval_applicable"]
            else None
        )
        cause = text_causes.get(question_id, "success")
        if cause == "retrieval_failure" and retrieval_ok is not False:
            raise ValueError(f"検索失敗注釈とTop-8結果が矛盾します: {question_id}")
        if cause == "classification_failure" and record["classification_ok"]:
            raise ValueError(f"分類失敗注釈とラベル結果が矛盾します: {question_id}")
        factors = record.get("classification_factors")
        old_label = _old_label(factors) if factors else None
        ledger.append(
            {
                "id": question_id,
                "modality": "text",
                "primary_cause": cause,
                "retrieval_ok": retrieval_ok,
                "expected_label": record["expected_label"],
                "candidate_label": record["predicted_label"],
                "candidate_classification_ok": record["classification_ok"],
                "previous_decision_label": old_label,
                "previous_decision_classification_ok": (
                    old_label == record["expected_label"] if old_label else False
                ),
                "error": record["error"],
            }
        )

    for scenario_id, record in visual.items():
        cause = visual_causes.get(scenario_id, "success")
        if cause == "retrieval_failure" and record["required_fixture_retrieved"]:
            raise ValueError(f"図表検索失敗注釈と結果が矛盾します: {scenario_id}")
        if cause == "classification_failure" and record["classification_ok"]:
            raise ValueError(f"図表分類失敗注釈と結果が矛盾します: {scenario_id}")
        expected_label = {
            "grounded": "根拠十分",
            "needs_judgment": "判断要",
            "insufficient_documents": "文書不足",
        }[record["expected_classification"]]
        factors = record["classification_factors"]
        old_label = _old_label(factors)
        ledger.append(
            {
                "id": scenario_id,
                "modality": "visual",
                "primary_cause": cause,
                "retrieval_ok": record["required_fixture_retrieved"],
                "expected_label": expected_label,
                "candidate_label": record["predicted_label"],
                "candidate_classification_ok": record["classification_ok"],
                "previous_decision_label": old_label,
                "previous_decision_classification_ok": old_label == expected_label,
                "error": record["error"],
            }
        )

    by_modality = {}
    for modality in ("text", "visual"):
        selected = [row for row in ledger if row["modality"] == modality]
        by_modality[modality] = dict(
            sorted(Counter(row["primary_cause"] for row in selected).items())
        )
    combined = dict(sorted(Counter(row["primary_cause"] for row in ledger).items()))
    production_causes = []
    for row in ledger:
        cause = row["primary_cause"]
        if (
            cause == "classification_failure"
            and row["previous_decision_classification_ok"]
        ):
            cause = "success"
        production_causes.append(cause)
    production_combined = dict(sorted(Counter(production_causes).items()))
    summary = {
        "total": len(ledger),
        "by_modality": by_modality,
        "combined": combined,
        "production_decision_v1_combined": production_combined,
        "candidate_classification_correct": sum(
            row["candidate_classification_ok"] for row in ledger
        ),
        "previous_decision_classification_correct": sum(
            row["previous_decision_classification_ok"] for row in ledger
        ),
        "decision_regressions": [
            row["id"]
            for row in ledger
            if row["previous_decision_classification_ok"]
            and not row["candidate_classification_ok"]
        ],
        "decision_improvements": [
            row["id"]
            for row in ledger
            if not row["previous_decision_classification_ok"]
            and row["candidate_classification_ok"]
        ],
    }
    return {"summary": summary, "ledger": ledger}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-records", type=Path, required=True)
    parser.add_argument("--visual-records", type=Path, required=True)
    parser.add_argument("--top-k", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"結果は上書きしません: {args.output}")
    result = analyze(
        _read_jsonl(args.text_records, "question_id"),
        _read_jsonl(args.visual_records, "scenario_id"),
        _read_json(args.top_k),
        _read_json(args.review),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
