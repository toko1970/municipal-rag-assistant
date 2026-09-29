"""Build the reviewed benchmark for comparing answer-classifier models."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from config import BASE_DIR, TOP_K
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.evaluate_retrieved_text_regression import (
    DEFAULT_DOCUMENT_CACHE,
    DEFAULT_QUERY_CACHE,
    prepare_text_corpus,
)


BASE_CASES = BASE_DIR / "eval/classification_prompt_development_cases_v2.json"
TEXT_RECORDS = (
    BASE_DIR
    / "eval/results/retrieved_text_regression_e24d7d4_v2/evaluation/records.jsonl"
)
OUTPUT = BASE_DIR / "eval/classifier_model_benchmark_v1.json"

FACTOR_KEYS = (
    "retrieval_sufficient",
    "answer_fully_supported",
    "requires_case_facts",
    "requires_policy_judgment",
    "version_conflict",
)


def factors(
    retrieval: bool,
    supported: bool,
    case_facts: bool = False,
    policy: bool = False,
    version: bool = False,
) -> dict[str, bool]:
    return {
        "retrieval_sufficient": retrieval,
        "answer_fully_supported": supported,
        "requires_case_facts": case_facts,
        "requires_policy_judgment": policy,
        "version_conflict": version,
    }


BASE_ANNOTATIONS: dict[str, tuple[dict[str, bool], str, str]] = {
    "CPD-T01": (factors(True, True), "approved", "基準日と境界値が質問内にあり、根拠から一意に決まる。"),
    "CPD-T02": (factors(True, True), "approved", "支給日が根拠に明記されている。"),
    "CPD-T03": (factors(True, True), "approved", "本人名義という明示条件をそのまま適用できる。"),
    "CPD-T04": (factors(True, True, case_facts=True), "approved", "結論を変える実通勤距離が質問にない。"),
    "CPD-T05": (factors(True, True, case_facts=True, policy=True), "approved", "職員事情が不足し、事情を踏まえた決定にも所管判断が残る。"),
    "CPD-T06": (factors(False, False), "approved", "取得根拠が質問と無関係で、回答claimもない。"),
    "CPD-V01": (factors(True, True), "approved", "90分以上という表の境界を直接適用できる。"),
    "CPD-V02": (factors(True, True), "approved", "flow上の状態と次工程がすべて質問にある。"),
    "CPD-V03": (factors(True, True), "approved", "30分未満の分岐を直接適用できる。"),
    "CPD-V04": (factors(True, True, case_facts=True), "approved", "事前講習の修了状況が不足している。"),
    "CPD-V05": (factors(True, True, case_facts=True), "approved", "金額を決める実作業時間が不足している。"),
    "CPD-V06": (factors(False, False), "approved", "保存年限を示す根拠がなく、回答claimもない。"),
    "CPD-T07": (factors(True, True, case_facts=True), "approved", "扶養実態と生計維持関係が不足している。"),
    "CPD-V07": (factors(True, True), "approved", "flowの二条件が質問内で充足している。"),
}

TEXT_ANNOTATIONS: dict[str, tuple[dict[str, bool], str, str, str]] = {
    "Q006": (factors(True, True), "approved", "observed_failure", "質問はこの規程だけで確定できるかを聞いており、別規程によると取得根拠から答えられる。"),
    "Q046": (factors(True, True), "approved", "hard_negative", "質問が求める確認先は取得根拠から一意に答えられる。"),
    "Q076": (factors(True, True), "approved", "observed_failure", "質問はこの規程だけで割合を判断できるかを聞いており、個別規程によると取得根拠から答えられる。"),
    "Q086": (factors(True, True), "approved", "hard_negative", "質問は一括返納が必須かを聞いており、必須ではないと答えられる。"),
    "Q121": (factors(True, True), "approved", "hard_negative", "基準日と施行日から適用版と境界値を解決できる。"),
    "Q126": (factors(True, True), "approved", "observed_failure", "日付、距離、通勤手段が質問内にあり結論が一意に決まる。"),
    "Q176": (factors(True, True), "approved", "observed_failure", "質問は自転車通勤なら必ず支給できるかを聞いており、複数要件があるため必ずではないと答えられる。"),
    "Q196": (factors(True, True), "approved", "hard_negative", "質問は家賃要件だけを聞いており、住居届提出状況は結論に不要である。"),
    "Q201": (factors(True, True), "approved", "hard_negative", "2025年9月には旧基準を一意に適用できる。"),
    "Q231": (factors(True, True), "approved", "hard_negative", "一つの手順根拠から処理順を回答できる。"),
    "Q281": (factors(True, True), "approved", "hard_negative", "発生日から改正前ルールを一意に適用できる。"),
    "Q286": (factors(True, True), "approved", "hard_negative", "発生日から改正後ルールを一意に適用できる。"),
    "Q301": (factors(True, True), "approved", "observed_failure", "質問は所属で即決できるかを聞いており、一律判断できないと取得根拠から答えられる。"),
    "Q316": (factors(True, True), "approved", "hard_negative", "質問が求める期限後の受付可否は取得根拠から答えられる。"),
    "Q451": (factors(False, False), "approved", "factor_control", "退職手当の計算式を示す根拠がない。"),
    "Q456": (factors(False, False), "approved", "factor_control", "育児休業中の支給割合を示す根拠がない。"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {row["question_id"]: row for row in rows}


def normalize_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": claim["claim_id"],
            "ordinal": claim["ordinal"],
            "text": claim["text"],
            "evidence_element_ids": claim["evidence_element_ids"],
            "evidence_kind": claim.get("evidence_kind", "text"),
        }
        for claim in claims
    ]


def oracle_cases() -> list[dict[str, Any]]:
    source = read_json(BASE_CASES)
    cases = []
    for case in source["cases"]:
        expected, status, rationale = BASE_ANNOTATIONS[case["case_id"]]
        cases.append(
            {
                "case_id": case["case_id"],
                "modality": case["modality"],
                "role": "factor_control",
                "source": {"kind": "oracle_control", "source_id": case["case_id"]},
                "question": case["question"],
                "evidence": [
                    {
                        "element_id": item["element_id"],
                        "content": item["content"],
                    }
                    for item in case["evidence"]
                ],
                "generated_answer": case["generated_answer"],
                "expected_label": case["expected_label"],
                "expected_factors": expected,
                "annotation_status": status,
                "annotation_rationale": rationale,
            }
        )
    return cases


def synthetic_cases() -> list[dict[str, Any]]:
    rows = [
        (
            "CMB-T01",
            "基準日を示さず、旧基準と新基準で結論が異なる場合はどちらを使いますか？",
            "旧基準は2.0km以上、新基準は1.5km以上とする。適用日の情報はない。",
            "適用版を一意に決められません。",
            factors(True, True, version=True),
            "適用日・優先規則がなく、結論に関係する版競合が残る。",
        ),
        (
            "CMB-T02",
            "改定日をまたぐ期間の手当額は改定前後のどちらで計算しますか？",
            "改定前は月額8,000円、改定後は9,000円。施行日は示すが期間をまたぐ場合の規則はない。",
            "期間をまたぐ場合の適用規則がないため確認が必要です。",
            factors(True, True, version=True),
            "期間をまたぐ適用規則がなく、版を一意に決められない。",
        ),
        (
            "CMB-T03",
            "期限後申請を遡及して認定してよいですか？",
            "期限後申請の遡及認定は、個別事情と制度運用への影響を踏まえて所管課が決定する。",
            "所管課の決定が必要です。",
            factors(True, True, policy=True),
            "必要事実が揃っても、根拠が所管課の裁量判断を明示している。",
        ),
        (
            "CMB-V01",
            "フローで管理者確認へ進んだ申請はそのまま承認してよいですか？",
            "不備なし → 管理者確認 → 管理者が可否を判断。判断基準は図に示されていない。",
            "管理者の判断が必要で、この図だけでは承認を確定できません。",
            factors(True, True, policy=True),
            "flowが裁量判断へ到達することを示すが、可否基準は示さない。",
        ),
        (
            "CMB-T04",
            "育児休業中の給与支給割合は何割ですか？",
            "給与は毎月21日に支給する。育児休業中の支給割合は記載されていない。",
            "",
            factors(False, False),
            "取得根拠に質問された支給割合がなく、支持できる回答claimもない。",
        ),
        (
            "CMB-V02",
            "この通勤経路図から駐車料金の上限額を確認できますか？",
            "自宅 → 駐車場 → 勤務公署。料金に関する記載はない。",
            "",
            factors(False, False),
            "図には経路だけがあり、質問された料金上限の根拠と回答claimがない。",
        ),
    ]
    result = []
    for case_id, question, evidence, claim, expected, rationale in rows:
        result.append(
            {
                "case_id": case_id,
                "modality": "visual" if "-V" in case_id else "text",
                "role": "factor_control",
                "source": {"kind": "synthetic_control", "source_id": case_id},
                "question": question,
                "evidence": [{"element_id": f"{case_id}-e1", "content": evidence}],
                "generated_answer": {
                    "schema_version": "1.0",
                    "claims": (
                        [
                            {
                                "claim_id": "claim-1",
                                "ordinal": 1,
                                "text": claim,
                                "evidence_element_ids": [f"{case_id}-e1"],
                                "evidence_kind": "flow_edge" if case_id.endswith("V01") else "text",
                            }
                        ]
                        if claim
                        else []
                    ),
                    "missing_conditions": [] if claim else ["質問へ答える根拠文書"],
                },
                "expected_label": "文書不足" if not expected["retrieval_sufficient"] else "判断要",
                "expected_factors": expected,
                "annotation_status": "approved",
                "annotation_rationale": rationale,
            }
        )
    return result


def regression_cases() -> list[dict[str, Any]]:
    records = read_jsonl(TEXT_RECORDS)
    selected = [records[question_id] for question_id in TEXT_ANNOTATIONS]
    index = prepare_text_corpus(DEFAULT_DOCUMENT_CACHE)
    vectors = load_baseline_query_vectors(DEFAULT_QUERY_CACHE, selected)
    result = []
    for question_id, (expected, status, role, rationale) in TEXT_ANNOTATIONS.items():
        row = records[question_id]
        hits = index.search(vectors[row["question"]], TOP_K)
        expected_ids = [item["element_id"] for item in row["retrieved"]]
        actual_ids = [str(hit.element.id) for hit in hits]
        if expected_ids != actual_ids:
            raise ValueError(f"保存済みTop-{TOP_K}を再現できません: {question_id}")
        evidence = [
            {
                "element_id": str(hit.element.id),
                "content": "\n".join(
                    part
                    for part in (
                        hit.element.document_name,
                        hit.element.heading,
                        hit.element.content,
                    )
                    if part
                ),
            }
            for hit in hits
        ]
        result.append(
            {
                "case_id": f"REG-{question_id}",
                "modality": "text",
                "role": role,
                "source": {"kind": "retrieved_regression", "source_id": question_id},
                "question": row["question"],
                "evidence": evidence,
                "generated_answer": {
                    "schema_version": "1.0",
                    "claims": normalize_claims(row["claims"]),
                    "missing_conditions": row["missing_conditions"],
                },
                "expected_label": (
                    "根拠十分"
                    if question_id in {"Q006", "Q046", "Q076", "Q086", "Q176", "Q301", "Q316"}
                    else row["expected_label"]
                ),
                "expected_factors": expected,
                "annotation_status": status,
                "annotation_rationale": rationale,
            }
        )
    return result


def build() -> dict[str, Any]:
    cases = oracle_cases() + synthetic_cases() + regression_cases()
    return {
        "schema_version": "1.0",
        "dataset_version": "classifier-model-benchmark-v1",
        "split": "development",
        "review_status": "approved",
        "case_count": len(cases),
        "expected_counts": dict(Counter(case["expected_label"] for case in cases)),
        "factor_true_counts": {
            key: sum(case["expected_factors"][key] for case in cases)
            for key in FACTOR_KEYS
        },
        "modality_counts": dict(Counter(case["modality"] for case in cases)),
        "source_hashes": {
            str(BASE_CASES.relative_to(BASE_DIR)): sha256(BASE_CASES),
            str(TEXT_RECORDS.relative_to(BASE_DIR)): sha256(TEXT_RECORDS),
            str(DEFAULT_DOCUMENT_CACHE.relative_to(BASE_DIR)): sha256(DEFAULT_DOCUMENT_CACHE),
            str(DEFAULT_QUERY_CACHE.relative_to(BASE_DIR)): sha256(DEFAULT_QUERY_CACHE),
        },
        "cases": cases,
    }


def main() -> None:
    dataset = build()
    OUTPUT.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {OUTPUT.relative_to(BASE_DIR)} cases={dataset['case_count']} "
        f"review_status={dataset['review_status']}"
    )


if __name__ == "__main__":
    main()
