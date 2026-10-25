"""Prompt construction and evidence serialization for query flows."""

from __future__ import annotations

import json
from uuid import UUID

from src.asset_store import VisualEvidenceAsset
from src.contracts import SearchHit


def _evidence_payload(
    hits: list[SearchHit],
    visual_assets: dict[UUID, VisualEvidenceAsset] | None = None,
    *,
    display_content: dict[UUID, bytes] | None = None,
) -> list[dict]:
    result = []
    visual_assets = visual_assets or {}
    display_content = display_content or {}
    attachment_indexes = {
        element_id: index for index, element_id in enumerate(visual_assets, start=1)
    }
    for hit in hits:
        payload = {
            "element_id": str(hit.element.id),
            "chunk_id": str(hit.element.id),
            "document_id": str(hit.element.document_id),
            "document_name": hit.element.document_name,
            "heading": hit.element.heading,
            "content": hit.element.content,
            "page_number": hit.element.page_number,
            "score": round(hit.score, 6),
            "source": hit.element.metadata.get("source", ""),
            "element_type": hit.element.element_type,
            "visual_extraction": hit.element.metadata.get("visual_extraction"),
        }
        asset = visual_assets.get(hit.element.id)
        if asset is not None:
            payload["visual_asset"] = {
                "mime_type": asset.mime_type,
                "page_number": asset.page_number,
                "sha256": asset.sha256,
                "bbox": asset.bbox,
                "attachment_index": attachment_indexes[hit.element.id],
            }
            if hit.element.id in display_content:
                payload["visual_asset"]["content"] = display_content[hit.element.id]
        result.append(payload)
    return result


def build_generation_prompt(
    question: str,
    hits: list[SearchHit],
    visual_assets: dict[UUID, VisualEvidenceAsset] | None = None,
) -> str:
    evidence = json.dumps(_evidence_payload(hits, visual_assets), ensure_ascii=False)
    return (
        "次の質問へ、取得根拠だけを使って回答してください。自由文の最終回答や分類は返さず、"
        "answer-output-v1のJSONだけを返してください。すべてのclaimにelement_idを引用してください。\n"
        "画像が添付される場合、visual_asset.attachment_indexが添付順（1始まり）です。\n"
        f"質問: {question}\n取得根拠: {evidence}"
    )


def build_classification_prompt(
    question: str, hits: list[SearchHit], answer_data: dict
) -> str:
    return build_classification_prompt_v1_from_payload(
        question, _evidence_payload(hits), answer_data
    )


def _classification_payload(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    return json.dumps(
        {
            "question": question,
            "retrieved_evidence": evidence,
            "generated_answer": answer_data,
        },
        ensure_ascii=False,
    )


def build_classification_prompt_v1_from_payload(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    payload = _classification_payload(question, evidence, answer_data)
    return (
        "classification-output-v1に従い、ラベルではなく5つの判定要因をJSONで返してください。"
        "corpus全体に答えが存在するかは判定しないでください。\n"
        f"判定対象: {payload}"
    )


def build_classification_prompt_v2(
    question: str, hits: list[SearchHit], answer_data: dict
) -> str:
    payload = _classification_payload(question, _evidence_payload(hits), answer_data)
    return (
        "classification-output-v1に従い、ラベルではなく5つの判定要因をJSONで返してください。"
        "corpus全体に答えが存在するかは判定しないでください。\n"
        "answer-output-v2のmissing_conditionsは、Generatorが残した未解決条件です。"
        "質問に明記された事実は回答上の既知事実として扱い、事実が質問に書かれていることだけを理由に"
        "requires_case_facts=trueにしないでください。\n"
        "date_calculationsから追加された具体日claimはアプリケーションが検証済みです。"
        "起算日、日数、数え方が揃っている場合、計算結果を再確認するためだけに"
        "requires_case_facts=trueにしないでください。\n"
        "質問が『所属だけで決められるか』『確認先はどこか』を尋ね、根拠からその可否や確認先を"
        "一意に答えられる場合は、実際の支給判断と区別してください。"
        "実際の結論に制度所管課の裁量が残る場合だけrequires_policy_judgment=trueです。\n"
        "基準日そのものが質問にない場合はrequires_case_factsです。必要な基準日が揃っても適用版を"
        "一意に決められない場合だけversion_conflictです。\n"
        f"判定対象: {payload}"
    )


def build_deadline_classification_prompt(
    question: str, hits: list[SearchHit], answer_data: dict
) -> str:
    payload = _classification_payload(question, _evidence_payload(hits), answer_data)
    return (
        "classification-output-v1に従い、ラベルではなく5つの判定要因をJSONで返してください。"
        "corpus全体に答えが存在するかは判定しないでください。\n"
        "質問に明記された起算日は回答上の既知事実です。"
        "date_calculationsを基にアプリケーションが追加した具体日claimは検証済みです。"
        "起算日、暦日数、数え方が揃っている場合、計算結果を再確認するためだけに"
        "requires_case_facts=trueにしないでください。\n"
        f"判定対象: {payload}"
    )
