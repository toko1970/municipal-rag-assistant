"""Question Contract v1.1 candidate with source-grounded spans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "design/schemas/question-contract-v1.1-candidate.schema.json"
)
PROMPT_VERSION = "question-contract-v1.1-candidate"


@dataclass(frozen=True)
class QuestionFacetV11:
    facet_id: str
    request_quote: str
    response_shape: str
    scope_quotes: tuple[str, ...]


@dataclass(frozen=True)
class InputFactV11:
    fact_id: str
    source_quote: str
    fact_type: str
    facet_ids: tuple[str, ...]


@dataclass(frozen=True)
class QuestionContractV11:
    facets: tuple[QuestionFacetV11, ...]
    input_facts: tuple[InputFactV11, ...]


class QuestionContractV11Error(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


@lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def build_prompt(question: str) -> str:
    return (
        "質問だけを読み、question-contract-v1.1-candidateのJSONを返してください。\n"
        "規則:\n"
        "1. requested_facetsには、質問者が明示的に答えを求めた項目だけを入れます。"
        "背景条件、確認手続、関連する注意事項を独立facetにしません。\n"
        "2. request_quoteは、質問中で回答を求めている最小限の連続した原文を、一字も"
        "言い換えずコピーします。\n"
        "3. response_shapeは回答の形です。可否=yes_no、金額=amount、日時=date_or_time、"
        "列挙=list、理由や扱いの説明=explanation、どれにも当たらない場合だけotherです。\n"
        "4. 一つの要求に複数の日付・対象があり、対象ごとに答えが変わり得る場合はfacetを"
        "分けます。同じrequest_quoteを使ってよく、各facetのscope_quotesへ区別する対象の"
        "原文をコピーします。答えが一つならscope_quotesは空配列です。\n"
        "5. input_factsには回答へ適用するため質問に明記された日付、金額、数量、条件、"
        "対象、出来事を記録します。source_quoteは質問から一字も言い換えずコピーし、"
        "推測を加えません。\n"
        "6. facet_idとfact_idは1から連続させます。\n"
        "例1: 質問『A日に1時間、B日に2時間実施した。各日の支給額は？』なら、"
        "request_quote『各日の支給額は？』を共有し、scope_quotes『A日』『B日』の"
        "amount facetを2件作ります。\n"
        "例2: 質問『登録済みだが証明番号は不明。申請できますか？』なら、"
        "yes_no facetはrequest_quote『申請できますか？』だけです。証明番号の確認方法を"
        "facetへ追加せず、条件はinput_factsへ置きます。\n"
        f"質問: {question}"
    )


def _require_contiguous(ids: list[str], prefix: str) -> None:
    expected = [f"{prefix}-{index}" for index in range(1, len(ids) + 1)]
    if ids != expected:
        raise QuestionContractV11Error(
            f"{prefix} IDは1から連続させてください", code="NON_CONTIGUOUS_ID"
        )


def _require_source_quote(question: str, quote: str, code: str) -> None:
    if quote not in question:
        raise QuestionContractV11Error(
            "引用が元質問の連続した部分文字列ではありません", code=code
        )


def parse(data: dict[str, Any], *, question: str) -> QuestionContractV11:
    try:
        jsonschema.Draft202012Validator(
            schema(), format_checker=jsonschema.FormatChecker()
        ).validate(data)
    except jsonschema.ValidationError as exc:
        location = ".".join(map(str, exc.absolute_path)) or "top-level"
        raise QuestionContractV11Error(
            f"schema違反 ({location}): {exc.message}", code="SCHEMA_INVALID"
        ) from exc
    if data["status"] != "SUCCESS":
        raise QuestionContractV11Error(
            str(data.get("error_code") or "CONTRACT_FAILED"),
            code="CONTRACT_FAILED",
        )

    facets = tuple(
        QuestionFacetV11(
            facet_id=row["facet_id"],
            request_quote=row["request_quote"],
            response_shape=row["response_shape"],
            scope_quotes=tuple(row["scope_quotes"]),
        )
        for row in data["requested_facets"]
    )
    facts = tuple(
        InputFactV11(
            fact_id=row["fact_id"],
            source_quote=row["source_quote"],
            fact_type=row["fact_type"],
            facet_ids=tuple(row["applies_to_facet_ids"]),
        )
        for row in data["input_facts"]
    )
    _require_contiguous([row.facet_id for row in facets], "facet")
    _require_contiguous([row.fact_id for row in facts], "fact")
    facet_ids = {row.facet_id for row in facets}
    for facet in facets:
        _require_source_quote(question, facet.request_quote, "REQUEST_QUOTE_NOT_IN_QUESTION")
        for quote in facet.scope_quotes:
            _require_source_quote(question, quote, "SCOPE_QUOTE_NOT_IN_QUESTION")
    for fact in facts:
        _require_source_quote(question, fact.source_quote, "FACT_QUOTE_NOT_IN_QUESTION")
        if not set(fact.facet_ids) <= facet_ids:
            raise QuestionContractV11Error(
                "入力事実が未知のfacetを参照しています", code="UNKNOWN_FACET"
            )
    facet_keys = [
        (row.request_quote, row.response_shape, row.scope_quotes) for row in facets
    ]
    if len(facet_keys) != len(set(facet_keys)):
        raise QuestionContractV11Error(
            "同じ要求と対象のfacetが重複しています", code="DUPLICATE_FACET"
        )
    return QuestionContractV11(facets=facets, input_facts=facts)
