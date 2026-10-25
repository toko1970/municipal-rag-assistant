"""Prompt builders for the facet based query flow."""

from __future__ import annotations

import json
from uuid import UUID

from src.asset_store import VisualEvidenceAsset
from src.contracts import SearchHit
from src.query_prompts import _evidence_payload


def build_question_contract_prompt(question: str) -> str:
    return (
        "質問だけを読み、question-contract-v1のJSONを返してください。"
        "requested_facetsは質問が直接求める回答項目へ分け、input_factsには質問に明記された"
        "日付・金額・数量・条件・対象・出来事だけを記録してください。input_factsから回答分類を決めず、"
        "epistemic_status等の確実性ラベルを追加しないでください。\n"
        f"質問: {question}"
    )


def build_generation_prompt_v3(
    question: str,
    question_contract: dict,
    hits: list[SearchHit],
    visual_assets: dict[UUID, VisualEvidenceAsset] | None = None,
) -> str:
    payload = {
        "question": question,
        "question_contract": question_contract,
        "retrieved_evidence": _evidence_payload(hits, visual_assets),
    }
    return (
        "answer-output-v3-candidateに従い、取得根拠だけを使ったfacet付きclaimを返してください。"
        "質問の各requested facetについて、結論に必要な規則・事実が根拠または質問内のinput_factにそろうかを先に確認してください。"
        "根拠にない規則や、質問にも根拠にもない対象者の事実を補ってはいけません。"
        "各claimは短い原子的主張とし、答えるfacet、使用するquestion input、検証済み計算、文書根拠をIDで参照します。"
        "claim_typeはpolicy_rule（制度一般の規則）、case_fact（対象者の事実）、conditional（条件付き説明）、"
        "case_outcome（対象者の認定・可否）、action_recommendation（対象者への確定処理の推奨）から選びます。"
        "case_outcomeとaction_recommendationは、結論に必要な未確認条件が一つでもあれば生成せず、"
        "条件付き説明またはpolicy_ruleとmissing_conditionsに分けてください。"
        "missing_conditionsはcase_fact/policy_judgment/version_conflictに型付けし、影響するfacet_idsと、"
        "その条件が成立しないと結論できないclaimのblocking_claim_idsを設定してください。"
        "該当claim側にもdepends_on_condition_idsを設定し、両方向のIDを一致させます。"
        "質問外の注意事項をmissing_conditionsへ追加しないでください。自由文の最終表示や回答分類は返さないでください。\n"
        f"生成対象: {json.dumps(payload, ensure_ascii=False)}"
    )


def build_classification_prompt_v2(
    question: str,
    question_contract: dict,
    hits: list[SearchHit],
    answer_data: dict,
) -> str:
    payload = {
        "question": question,
        "question_contract": question_contract,
        "retrieved_evidence": _evidence_payload(hits),
        "generated_answer": answer_data,
    }
    return (
        "classification-output-v2-candidateに従い、最終ラベルではなく各requested facetの"
        "evidence_coverage、claim_support、human_review_requirementsを返してください。"
        "policy_rule等の一般説明とcase_outcome/action_recommendationの個別結論を区別し、"
        "未解決条件が個別結論に関わる場合は該当condition_idsを参照してください。"
        "質問内の事実は文書根拠ではなく入力値です。文書に判断基準があり、その事実が結論を"
        "変える場合だけcase_factにします。文書に判断基準がない場合はevidence_coverageを"
        "insufficientとし、人による確認要件を作らないでください。\n"
        f"判定対象: {json.dumps(payload, ensure_ascii=False)}"
    )
