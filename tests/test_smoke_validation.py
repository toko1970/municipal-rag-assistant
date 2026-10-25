from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

import pytest

from src.smoke_validation import SMOKE_CASES, validate_smoke_result


CASES = {case.case_id: case for case in SMOKE_CASES}


def salary_result(*, structured=False):
    return {
        "request_id": "smoke-request",
        "answer_status": "SUCCESS",
        "degraded": False,
        "answer_label": "根拠十分",
        "answer": "回答分類: 根拠十分\n\n回答:\n毎月21日です。休日の場合は直前の営業日です。",
        "references": [{
            "document_id": str(uuid5(NAMESPACE_URL, "document:DOC-001"))
            if structured else "DOC-001",
            "document_name": "給与制度規程",
            "heading": "3. 給与支給日",
            "content": "職員の給与は毎月21日に支給する。",
        }],
        "generation": {"model": "fake"} if structured else {"finish_reason": "STOP"},
    }


@pytest.mark.parametrize("structured", [False, True])
def test_accepts_both_real_return_contract_shapes(structured):
    verdict = validate_smoke_result(salary_result(structured=structured), CASES["salary_day"])
    assert verdict.passed
    assert verdict.failure_kind is None
    assert verdict.semantic_review_status == "PENDING"


@pytest.mark.parametrize("changes,expected", [
    ({"answer_label": None}, "FORMAT_ERROR"),
    ({"answer": "  "}, "FORMAT_ERROR"),
    ({"answer": "回答分類: 根拠十分\n回答:\n根拠文書:\n給与制度規程"}, "FORMAT_ERROR"),
    ({"answer_status": "GENERATION_INCOMPLETE"}, "GENERATION_INCOMPLETE"),
    ({"generation": {"finish_reason": "MAX_TOKENS"}}, "GENERATION_INCOMPLETE"),
    ({"generation": {"finish_reason": "SAFETY"}}, "GENERATION_INCOMPLETE"),
    ({"degraded": True}, "PIPELINE_FAILURE"),
    ({"answer_status": "PROVIDER_ERROR"}, "PROVIDER_ERROR"),
    ({"answer_label": "判断要"}, "EXPECTATION_MISMATCH"),
    ({"references": []}, "MISSING_REFERENCE"),
    ({"references": None}, "FORMAT_ERROR"),
    ({"references": [{"document_id": "DOC-004", "content": "無関係な根拠"}]}, "MISSING_REFERENCE"),
    ({"generation": "not a mapping"}, "FORMAT_ERROR"),
])
def test_rejects_incomplete_or_inconsistent_result(changes, expected):
    result = salary_result()
    result.update(changes)
    verdict = validate_smoke_result(result, CASES["salary_day"])
    assert not verdict.passed
    assert verdict.failure_kind == expected
    assert verdict.reasons


def test_generic_status_does_not_replace_actual_answer_status_contract():
    result = salary_result()
    del result["answer_status"]
    result["status"] = "SUCCESS"
    verdict = validate_smoke_result(result, CASES["salary_day"])
    assert not verdict.passed
    assert verdict.failure_kind == "FORMAT_ERROR"


@pytest.mark.parametrize("result", [None, [], "SUCCESS", {"answer_status": 42}])
def test_rejects_malformed_return_without_raising(result):
    verdict = validate_smoke_result(result, CASES["salary_day"])
    assert not verdict.passed
    assert verdict.failure_kind == "FORMAT_ERROR"


def test_missing_document_accepts_zero_references_and_structured_guidance():
    result = salary_result(structured=True)
    result.update({
        "answer_label": "文書不足",
        "answer": "回答分類: 文書不足\n\n今回取得した根拠では回答を確認できませんでした。",
        "references": [],
    })
    verdict = validate_smoke_result(result, CASES["missing_document"])
    assert verdict.passed
    # Only the return contract is automatic; the explanation needs real review.
    assert verdict.semantic_review_status == "PENDING"
    result["answer"] = "回答分類: 文書不足"
    assert not validate_smoke_result(result, CASES["missing_document"]).passed


def test_visual_case_requires_expected_document_and_loaded_image_on_same_reference():
    result = salary_result()
    expected = {
        "document_id": "visual-demo-table_dev_001",
        "document_name": "通勤手当 支給額・区分表（架空）",
        "content": "常勤職員 月15日以上 12,000円 上限額",
    }
    result["references"] = [expected]
    assert validate_smoke_result(result, CASES["visual_table"]).failure_kind == "MISSING_REFERENCE"
    result["references"].append({
        "document_id": "different-document",
        "content": "別の図表",
        "visual_asset": {"content": b"image", "mime_type": "image/png", "page_number": 1},
    })
    assert not validate_smoke_result(result, CASES["visual_table"]).passed
    expected["visual_asset"] = {"content": b"image", "mime_type": "image/png", "page_number": 1}
    assert validate_smoke_result(result, CASES["visual_table"]).passed
    expected["visual_asset"]["content"] = b""
    assert not validate_smoke_result(result, CASES["visual_table"]).passed


def test_expected_document_with_wrong_section_or_empty_content_is_not_enough():
    result = salary_result()
    result["references"][0]["heading"] = "1. 目的"
    assert not validate_smoke_result(result, CASES["salary_day"]).passed


def test_malformed_reference_identifier_fails_without_throwing():
    result = salary_result()
    result["references"][0]["document_id"] = ["DOC-001"]
    assert validate_smoke_result(result, CASES["salary_day"]).failure_kind == "MISSING_REFERENCE"
    result = salary_result()
    result["references"][0]["content"] = " "
    assert not validate_smoke_result(result, CASES["salary_day"]).passed


def test_validation_does_not_mutate_answer_or_case():
    result = salary_result()
    before = deepcopy(result)
    validate_smoke_result(result, CASES["salary_day"])
    assert result == before


@pytest.mark.parametrize("body,expected_pass", [
    ("---", False), ("* * *\n_ _ _\n###\n>\n```", False),
    ("給与は毎月21日に支給します。", True), ("A normal answer.", True), ("42", True),
])
def test_body_requires_content_beyond_markdown_formatting(body, expected_pass):
    result = salary_result()
    result["answer"] = f"回答分類: 根拠十分\n回答:\n{body}\n根拠文書:\n給与制度規程"
    verdict = validate_smoke_result(result, CASES["salary_day"])
    assert verdict.passed is expected_pass
    if not expected_pass:
        assert verdict.failure_kind == "FORMAT_ERROR"


def test_missing_counting_rule_blocks_sufficient_but_does_not_claim_semantic_pass():
    result = salary_result()
    result["references"] = [{
        "document_id": "DOC-004", "document_name": "届出・手続きマニュアル",
        "heading": "2.2 提出期限", "content": "住所変更日から14日以内に提出すること。",
    }]
    assert not validate_smoke_result(result, CASES["missing_counting_rule"]).passed
    for label in ("判断要", "文書不足"):
        result["answer_label"] = label
        result["answer"] = f"回答分類: {label}\n回答:\n起算規則が不足するため期限日を確定できません。"
        verdict = validate_smoke_result(result, CASES["missing_counting_rule"])
        assert verdict.passed
        assert verdict.semantic_review_status == "PENDING"


@pytest.mark.parametrize("flow", ["candidate", "production"])
def test_checks_real_flow_outputs_with_only_external_boundaries_faked(flow):
    from types import SimpleNamespace
    from uuid import uuid4

    from src.contracts import IndexableElement, SearchHit
    from src.llm_provider import LLMResult, StructuredLLMResult
    from src.query_service import answer_question
    from src.simple_rag_flow import generate_simple_qdrant_answer

    element = IndexableElement(
        id=uuid4(), document_id=uuid5(NAMESPACE_URL, "document:DOC-001"), version_id=uuid4(),
        document_name="給与制度規程", heading="3. 給与支給日",
        content="毎月21日、土日祝の場合は直前営業日に支給する。", metadata={"document_key": "DOC-001"},
    )
    hit = SearchHit(element, 0.9, 1)
    if flow == "candidate":
        generator = SimpleNamespace(generate=lambda _prompt: LLMResult(
            "fake", "fake-model", "回答分類: 根拠十分\n回答:\n毎月21日、土日祝の場合は直前営業日です。",
            finish_reason="STOP",
        ))
        result = generate_simple_qdrant_answer(
            CASES["salary_day"].question, retrieved_hits=[hit], generator=generator,
            prompt_variant="autoresearch_candidate", record_log=False,
        )
    else:
        generated = {"schema_version": "1.0", "claims": [{
            "claim_id": "claim-1", "ordinal": 1, "text": "毎月21日に支給します。",
            "evidence_element_ids": [str(element.id)], "evidence_kind": "text",
        }], "missing_conditions": []}
        classified = {"schema_version": "1.0", "status": "SUCCESS", "factors": {
            "retrieval_sufficient": True, "answer_fully_supported": True,
            "requires_case_facts": False, "requires_policy_judgment": False, "version_conflict": False,
        }, "confidence": 0.98, "error_code": None}

        def provider(data):
            return SimpleNamespace(provider_name="fake", model="fake-model",
                                   generate_structured=lambda _prompt, _schema: StructuredLLMResult("fake", "fake-model", data))

        logger = SimpleNamespace(start_request=lambda _q: uuid4(), record_retrieval=lambda *_args: None,
                                 record_generation_attempt=lambda *_args, **_kwargs: None,
                                 record_classification_attempt=lambda *_args, **_kwargs: None,
                                 record_answer_result=lambda *_args, **_kwargs: None)
        result = answer_question(
            CASES["salary_day"].question, embed_query=lambda _q: [0.1],
            vector_index=SimpleNamespace(search=lambda _vector, limit: [hit]),
            generator=provider(generated), classifier=provider(classified), event_logger=logger,
            answer_schema={"title": "answer"}, classification_schema={"title": "classification"},
        )
    verdict = validate_smoke_result(result, CASES["salary_day"])
    assert verdict.passed
    assert verdict.matched_evidence == ("DOC-001",)
