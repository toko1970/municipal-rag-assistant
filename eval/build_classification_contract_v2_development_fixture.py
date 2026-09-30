"""Build rubric-v2 development cases from saved opened-holdout outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS_PATH = (
    ROOT / "eval/results/text_holdout_v1_predictions_v10/predictions.jsonl"
)
REVIEWS_PATH = ROOT / "eval/results/text_holdout_v1_acceptance/content_review.jsonl"
OUTPUT_PATH = ROOT / "eval/classification_contract_v2_development_cases.json"


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_by_scenario(path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["scenario_id"]: row
        for row in _rows(path)
        if row["variant_type"] == "formal"
    }


ANNOTATIONS: dict[str, dict[str, Any]] = {
    "TH011": {
        "facets": [
            ("補助額", "amount"),
            ("具体的な提出期限日と時刻", "date"),
        ],
        "facts": [
            ("受験日は2027年10月10日", "date", ["facet-1", "facet-2"]),
            ("受験料は8,000円", "amount", ["facet-1"]),
            ("その他の条件は満たす", "condition", ["facet-1", "facet-2"]),
        ],
        "claim_links": [
            (["facet-1"], ["fact-1"], []),
            (["facet-1"], ["fact-1", "fact-2"], []),
            (["facet-2"], ["fact-1"], []),
        ],
        "condition": None,
        "assessments": [
            ("facet-1", ["claim-1", "claim-2"], "fully_supported", None),
            ("facet-2", ["claim-3"], "partially_supported", None),
        ],
        "expected_status": "GENERATION_INCOMPLETE",
        "expected_label": None,
        "rationale": "文書と期限規則は取得済みだが、具体日2027年10月30日正午を回答していない。",
    },
    "TH025": {
        "facets": [("補填可否を確定できるか", "eligibility")],
        "facts": [
            ("職員登録と勤務計画登録は済んでいる", "condition", ["facet-1"]),
            ("午前券の利用料900円を支払った", "amount", ["facet-1"]),
            ("施設認定コードが判読できない", "condition", ["facet-1"]),
        ],
        "claim_links": [
            (["facet-1"], ["fact-3"], []),
            (["facet-1"], ["fact-2", "fact-3"], []),
        ],
        "condition": "判読可能な施設認定コードとその有効性",
        "assessments": [
            (
                "facet-1",
                ["claim-1", "claim-2"],
                "fully_supported",
                "case_fact",
            )
        ],
        "expected_status": "SUCCESS",
        "expected_label": "判断要",
        "rationale": "文書に保留照会の基準があり、施設コードの確認が結論を変える。",
    },
    "TH031": {
        "facets": [("補助可否を確定できるか", "eligibility")],
        "facts": [
            ("登録・事前承認・受験実績は確認済み", "condition", ["facet-1"]),
            ("同一年度の受給歴が未照合", "condition", ["facet-1"]),
            ("本人は初回と申告している", "condition", ["facet-1"]),
        ],
        "claim_links": [
            (["facet-1"], ["fact-2", "fact-3"], []),
        ],
        "condition": "同一年度の補助受給歴",
        "assessments": [("facet-1", ["claim-1"], "fully_supported", "case_fact")],
        "expected_status": "SUCCESS",
        "expected_label": "判断要",
        "rationale": "文書に受給台帳照合の基準があり、本人申告だけでは結論が決まらない。",
    },
}


def _build_case(
    scenario_id: str,
    annotation: dict[str, Any],
    prediction: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    facets = [
        {
            "facet_id": f"facet-{index}",
            "requirement": requirement,
            "answer_type": answer_type,
        }
        for index, (requirement, answer_type) in enumerate(
            annotation["facets"], start=1
        )
    ]
    facts = [
        {
            "fact_id": f"fact-{index}",
            "text": text,
            "fact_type": fact_type,
            "applies_to_facet_ids": facet_ids,
        }
        for index, (text, fact_type, facet_ids) in enumerate(
            annotation["facts"], start=1
        )
    ]
    claims = []
    for source_claim, links in zip(
        prediction["claims"], annotation["claim_links"], strict=True
    ):
        facet_ids, input_fact_ids, calculation_ids = links
        claims.append(
            {
                **source_claim,
                "facet_ids": facet_ids,
                "input_fact_ids": input_fact_ids,
                "calculation_ids": calculation_ids,
                "evidence_kind": "text",
            }
        )

    condition_text = annotation["condition"]
    condition = []
    if condition_text:
        condition = [
            {
                "condition_id": "condition-1",
                "type": "case_fact",
                "description": condition_text,
                "facet_ids": ["facet-1"],
                "evidence_element_ids": claims[0]["evidence_element_ids"],
            }
        ]

    assessments = []
    claim_by_id = {claim["claim_id"]: claim for claim in claims}
    for facet_id, claim_ids, support, review_type in annotation["assessments"]:
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for claim_id in claim_ids
                for evidence_id in claim_by_id[claim_id]["evidence_element_ids"]
            )
        )
        requirements = []
        if review_type:
            requirements.append(
                {
                    "review_id": "review-1",
                    "type": review_type,
                    "description": condition_text,
                    "condition_ids": ["condition-1"],
                    "evidence_element_ids": condition[0]["evidence_element_ids"],
                }
            )
        assessments.append(
            {
                "facet_id": facet_id,
                "claim_ids": claim_ids,
                "claim_support": support,
                "evidence_coverage": "sufficient",
                "human_review_requirements": requirements,
                "evidence_element_ids": evidence_ids,
                "confidence": 1.0,
            }
        )

    return {
        "scenario_id": scenario_id,
        "variant_type": "formal",
        "source_question": prediction["question"],
        "source_predicted_label": prediction["answer_label"],
        "source_content_ok": review["content_ok"],
        "source_classification_ok": review["classification_ok"],
        "question_contract": {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "requested_facets": facets,
            "input_facts": facts,
            "error_code": None,
        },
        "answer_v3": {
            "schema_version": "3.0-candidate",
            "claims": claims,
            "missing_conditions": condition,
            "date_calculations": [],
        },
        "classification_v2": {
            "schema_version": "2.0-candidate",
            "status": "SUCCESS",
            "facet_assessments": assessments,
            "confidence": 1.0,
            "error_code": None,
        },
        "retrieved_element_ids": [row["element_id"] for row in prediction["retrieved"]],
        "expected_status": annotation["expected_status"],
        "expected_label": annotation["expected_label"],
        "rationale": annotation["rationale"],
    }


def build() -> dict[str, Any]:
    predictions = _source_by_scenario(PREDICTIONS_PATH)
    reviews = _source_by_scenario(REVIEWS_PATH)
    return {
        "schema_version": "1.0",
        "rubric_version": "classification-rubric-v2.0",
        "purpose": "opened_holdout_mechanism_test_only",
        "source_predictions": str(PREDICTIONS_PATH.relative_to(ROOT)),
        "source_predictions_sha256": _sha256(PREDICTIONS_PATH),
        "source_reviews": str(REVIEWS_PATH.relative_to(ROOT)),
        "source_reviews_sha256": _sha256(REVIEWS_PATH),
        "external_api_calls": 0,
        "cases": [
            _build_case(
                scenario_id, annotation, predictions[scenario_id], reviews[scenario_id]
            )
            for scenario_id, annotation in ANNOTATIONS.items()
        ],
    }


def main() -> None:
    result = build()
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote={OUTPUT_PATH.relative_to(ROOT)} cases={len(result['cases'])}")


if __name__ == "__main__":
    main()
