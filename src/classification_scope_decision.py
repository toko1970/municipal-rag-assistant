"""Deterministic validation and display decisions for scope classification."""

from __future__ import annotations

import jsonschema

from src.answering import DisplayAnswer, StructuredAnswer
from src.classification_scope_definition import scope_schema


def safe_failure(status: str, code: str) -> DisplayAnswer:
    text = (
        "回答の内容を十分に確認できませんでした。条件や質問を見直して、再度お試しください。"
        if status != "PROVIDER_ERROR"
        else "現在、回答の処理を完了できませんでした。時間をおいて再度お試しください。"
    )
    return DisplayAnswer(None, text, (), status, code)


def decide_scope_answer(
    data: dict, answer: StructuredAnswer, evidence_ids: set[str]
) -> DisplayAnswer:
    """Validate references, then apply the rubric; no generation failure label."""
    jsonschema.Draft202012Validator(scope_schema()).validate(data)
    claims = {c.claim_id: c for c in answer.claims}
    assessed = set()
    targets = data["targets"]
    names = [t["target"].strip() for t in targets]
    if any(not n for n in names) or len(names) != len(set(names)):
        raise ValueError("INVALID_TARGETS")
    for target in targets:
        refs = set(target["evidence_ids"])
        ids = set(target["claim_ids"])
        if not refs <= evidence_ids or not ids <= claims.keys():
            raise ValueError("UNKNOWN_REFERENCE")
        assessed.update(ids)
        if bool(ids) == (target["claim_support"] == "no_claim"):
            raise ValueError("CLAIM_SUPPORT_REFERENCE_MISMATCH")
        if target["evidence_sufficient"] and not refs:
            raise ValueError("RULE_WITHOUT_EVIDENCE")
        if target["claim_support"] == "supported":
            if not refs or any(
                not set(map(str, claims[cid].evidence_element_ids)) <= evidence_ids
                for cid in ids
            ):
                raise ValueError("SUPPORTED_WITHOUT_VALID_EVIDENCE")
        if not target["evidence_sufficient"] and target["reviews"]:
            raise ValueError("REVIEW_WITHOUT_RULE")
        for review in target["reviews"]:
            if not review["reason"].strip() or not set(review["evidence_ids"]) <= refs:
                raise ValueError("INVALID_REVIEW_EVIDENCE")
    if any(not t["evidence_sufficient"] for t in targets):
        return DisplayAnswer(
            "文書不足",
            "回答分類: 文書不足\n\n今回取得した根拠では回答を確認できませんでした。",
            (),
        )
    if (
        assessed != claims.keys()
        or not claims
        or any(
            t["claim_support"] != "supported" or not t["answer_complete"]
            for t in targets
        )
    ):
        return safe_failure("GENERATION_INCOMPLETE", "SUPPORT_OR_COMPLETENESS_FAILED")
    reviews = [r for t in targets for r in t["reviews"]]
    label = "判断要" if reviews else "根拠十分"
    lines = [f"回答分類: {label}", "", "回答:", *(f"- {c.text}" for c in answer.claims)]
    if reviews:
        lines.extend(
            [
                "",
                "確認が必要です: "
                + "、".join(dict.fromkeys(r["reason"] for r in reviews)),
            ]
        )
    return DisplayAnswer(label, "\n".join(lines), answer.claims)
