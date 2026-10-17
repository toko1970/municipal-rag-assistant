import copy
from uuid import UUID, uuid4

import pytest

from src.answering import parse_answer_output
from src.classification_scope_contract import decide_scope_answer, scope_schema
from src.contracts import IndexableElement, SearchHit
from src.llm_provider import StructuredLLMResult
from src.query_service import answer_question

EID = "c55b0157-7719-41aa-a57e-2516327dac2b"


def answer_data():
    return {
        "schema_version": "1.0",
        "claims": [
            {
                "claim_id": "claim-1",
                "ordinal": 1,
                "text": "単価は500円です。",
                "evidence_element_ids": [EID],
                "evidence_kind": "text",
            }
        ],
        "missing_conditions": [],
    }


def assessment():
    return {
        "schema_version": "scope-2.0",
        "confidence": 0.9,
        "targets": [
            {
                "target": "単価",
                "intent": "general_rule",
                "evidence_sufficient": True,
                "evidence_ids": [EID],
                "claim_ids": ["claim-1"],
                "claim_support": "supported",
                "answer_complete": True,
                "reviews": [],
            }
        ],
    }


@pytest.mark.parametrize(
    "change,status,label",
    [
        ({}, "SUCCESS", "根拠十分"),
        ({"answer_complete": False}, "GENERATION_INCOMPLETE", None),
        ({"claim_support": "unsupported"}, "GENERATION_INCOMPLETE", None),
        ({"evidence_sufficient": False}, "SUCCESS", "文書不足"),
        (
            {
                "reviews": [
                    {
                        "type": "case_fact",
                        "reason": "記録が未照合",
                        "evidence_ids": [EID],
                    }
                ]
            },
            "SUCCESS",
            "判断要",
        ),
    ],
)
def test_scope_decision_separates_failures(change, status, label):
    data = assessment()
    data["targets"][0].update(change)
    display = decide_scope_answer(data, parse_answer_output(answer_data()), {EID})
    assert display.status == status and display.label == label
    if status != "SUCCESS" or label == "文書不足":
        assert not display.visible_claims


def test_empty_claims_and_unassessed_extra_claims_fail_safely():
    data = assessment()
    data["targets"][0].update(
        claim_ids=[], claim_support="no_claim", answer_complete=True
    )
    answer = answer_data()
    answer["claims"] = []
    assert (
        decide_scope_answer(data, parse_answer_output(answer), {EID}).status
        == "GENERATION_INCOMPLETE"
    )
    data = assessment()
    answer = answer_data()
    answer["claims"].append(
        {
            **answer["claims"][0],
            "claim_id": "claim-2",
            "ordinal": 2,
            "text": "根拠外の主張",
        }
    )
    assert (
        decide_scope_answer(data, parse_answer_output(answer), {EID}).status
        == "GENERATION_INCOMPLETE"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("claim_ids", ["unknown"]),
        ("evidence_ids", [str(uuid4())]),
        ("claim_ids", []),
        ("claim_support", "no_claim"),
        ("reviews", [{"type": "case_fact", "reason": " ", "evidence_ids": [EID]}]),
    ],
)
def test_invalid_references_are_rejected(field, value):
    data = assessment()
    data["targets"][0][field] = value
    with pytest.raises(ValueError):
        decide_scope_answer(data, parse_answer_output(answer_data()), {EID})


def test_all_targets_must_be_complete_and_review_requires_rule():
    data = assessment()
    second = copy.deepcopy(data["targets"][0])
    second.update(
        target="提出先", claim_ids=[], claim_support="no_claim", answer_complete=False
    )
    data["targets"].append(second)
    assert (
        decide_scope_answer(data, parse_answer_output(answer_data()), {EID}).status
        == "GENERATION_INCOMPLETE"
    )
    second.update(
        evidence_sufficient=False,
        reviews=[{"type": "case_fact", "reason": "個別記録", "evidence_ids": [EID]}],
    )
    with pytest.raises(ValueError, match="REVIEW_WITHOUT_RULE"):
        decide_scope_answer(data, parse_answer_output(answer_data()), {EID})


class Provider:
    provider_name = "fake"
    model = "fake"

    def __init__(self, data):
        self.data = data
        self.calls = 0

    def generate_structured(self, prompt, schema):
        self.calls += 1
        if isinstance(self.data, Exception):
            raise self.data
        return StructuredLLMResult("fake", "fake", self.data)


class Logger:
    def __init__(self):
        self.events = []

    def start_request(self, question):
        return uuid4()

    def record_retrieval(self, request_id, hits):
        pass

    def record_generation_attempt(self, request_id, **kwargs):
        self.events.append(("generation", kwargs))

    def record_classification_attempt(self, request_id, **kwargs):
        self.events.append(("classification", kwargs))

    def record_answer_result(self, request_id, **kwargs):
        self.events.append(("answer", kwargs))


class Index:
    def search(self, vector, limit):
        return [
            SearchHit(
                IndexableElement(
                    id=UUID(EID),
                    document_id=uuid4(),
                    version_id=uuid4(),
                    document_name="架空規則",
                    heading="単価",
                    content="単価は500円。提出先は研修室。",
                ),
                1.0,
                1,
            )
        ]


@pytest.mark.parametrize(
    "generation,classification,expected",
    [
        (answer_data(), assessment(), "SUCCESS"),
        (answer_data(), {"bad": "schema"}, "PIPELINE_INCONSISTENCY"),
        (answer_data(), RuntimeError("network"), "PROVIDER_ERROR"),
        (answer_data(), ValueError("malformed json"), "CLASSIFICATION_FAILED"),
        ({"bad": "schema"}, assessment(), "GENERATION_FAILED"),
        (RuntimeError("network"), assessment(), "PROVIDER_ERROR"),
    ],
)
def test_candidate_flow_safe_returns_and_logs(generation, classification, expected):
    gen, cls, logger = Provider(generation), Provider(classification), Logger()
    result = answer_question(
        "単価は？",
        embed_query=lambda q: [0],
        vector_index=Index(),
        generator=gen,
        classifier=cls,
        event_logger=logger,
        answer_schema={},
        classification_schema=scope_schema(),
        scope_classification=True,
    )
    assert result["answer_status"] == expected
    assert logger.events[-1][0] == "answer"
    if expected != "SUCCESS":
        assert result["answer_label"] is None and not result["claims"]
        assert "500円" not in result["answer"]
    if generation != answer_data():
        assert cls.calls == 0


def test_generated_conditions_are_independently_adjudicated():
    raw = answer_data()
    raw["missing_conditions"] = ["質問していない実支給の照合"]
    assert (
        decide_scope_answer(assessment(), parse_answer_output(raw), {EID}).label
        == "根拠十分"
    )


@pytest.mark.parametrize(
    "confidence,bad_ref,keep_case,label",
    [
        (0.95, False, False, None),
        (0.4, False, False, "判断要"),
        (0.95, True, False, "判断要"),
        (0.95, False, True, None),
    ],
)
def test_scope_version_resolution_is_guarded(confidence, bad_ref, keep_case, label):
    from src.classification_scope_contract import classify_scope_answer

    data = assessment()
    data["targets"][0]["reviews"] = [
        {"type": "version_conflict", "reason": "版を確認", "evidence_ids": [EID]}
    ]
    if keep_case:
        data["targets"][0]["reviews"].append(
            {"type": "case_fact", "reason": "記録未照合", "evidence_ids": [EID]}
        )
    resolver = Provider(
        {
            "schema_version": "1.0",
            "status": "SUCCESS",
            "version_conflict": False,
            "resolution_basis": "question_date",
            "evidence_element_ids": [str(uuid4()) if bad_ref else EID],
            "confidence": confidence,
            "error_code": None,
        }
    )
    display, _, raw, metadata = classify_scope_answer(
        question="適用単価は？",
        evidence=[{"element_id": EID}],
        answer=parse_answer_output(answer_data()),
        answer_data=answer_data(),
        classifier=Provider(data),
        event_logger=Logger(),
        request_id=uuid4(),
        version_resolver=resolver,
        version_resolution_schema={},
    )
    assert display.label == label
    assert metadata["applied"] == (confidence >= 0.8 and not bad_ref)
    assert raw["targets"][0]["reviews"][0]["type"] == "version_conflict"
    assert metadata["raw_output"] == resolver.data
    if not bad_ref:
        assert metadata["resolution_basis"] == "question_date"
        assert metadata["confidence"] == confidence
    if confidence >= 0.8 and not bad_ref:
        assert display.status == "GENERATION_INCOMPLETE"
        assert not display.visible_claims
        assert metadata["status"] == "REVALIDATION_FAILED"


class SequenceProvider(Provider):
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.prompts = []

    def generate_structured(self, prompt, schema):
        self.calls += 1
        self.prompts.append(prompt)
        data = next(self.responses)
        if isinstance(data, Exception):
            raise data
        return StructuredLLMResult(
            "fake", "fake", data, input_tokens=11, output_tokens=7
        )


def resolved_version():
    return {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "version_conflict": False,
        "resolution_basis": "question_date",
        "evidence_element_ids": [EID],
        "confidence": 0.95,
        "error_code": None,
    }


@pytest.mark.parametrize(
    "mode,expected_label,expected_status",
    [
        ("complete", "根拠十分", "SUCCESS"),
        ("keep_case", "判断要", "SUCCESS"),
        ("keep_policy", "判断要", "SUCCESS"),
        ("unsupported", None, "GENERATION_INCOMPLETE"),
        ("incomplete", None, "GENERATION_INCOMPLETE"),
        ("changed_scope", None, "GENERATION_INCOMPLETE"),
        ("changed_claims", None, "GENERATION_INCOMPLETE"),
        ("version_disagreement", None, "GENERATION_INCOMPLETE"),
        ("low_confidence", None, "GENERATION_INCOMPLETE"),
        ("invalid_id", None, "GENERATION_INCOMPLETE"),
        ("malformed", None, "GENERATION_INCOMPLETE"),
        ("timeout", None, "GENERATION_INCOMPLETE"),
    ],
)
def test_resolved_version_revalidates_once_through_query_service(
    mode, expected_label, expected_status
):
    initial = assessment()
    initial["targets"][0]["reviews"] = [
        {"type": "version_conflict", "reason": "版が競合", "evidence_ids": [EID]}
    ]
    if mode in {"keep_case", "keep_policy"}:
        initial["targets"][0]["reviews"].append(
            {
                "type": "case_fact" if mode == "keep_case" else "policy_judgment",
                "reason": "元の確認事項",
                "evidence_ids": [EID],
            }
        )
    checked = assessment()
    if mode == "unsupported":
        checked["targets"][0]["claim_support"] = "unsupported"
    elif mode == "incomplete":
        checked["targets"][0]["answer_complete"] = False
    elif mode == "changed_scope":
        checked["targets"][0]["target"] = "別の対象"
    elif mode == "changed_claims":
        checked["targets"][0].update(claim_ids=[], claim_support="no_claim")
    elif mode == "version_disagreement":
        checked = copy.deepcopy(initial)
    elif mode == "low_confidence":
        checked["confidence"] = 0.4
    elif mode == "invalid_id":
        checked["targets"][0]["evidence_ids"] = [str(uuid4())]
    elif mode == "malformed":
        checked = {"bad": "schema"}
    elif mode == "timeout":
        checked = TimeoutError("timeout")
    cls = SequenceProvider([initial, checked])
    resolver, gen, logger = (
        Provider(resolved_version()),
        Provider(answer_data()),
        Logger(),
    )
    result = answer_question(
        "2027年の単価は？",
        embed_query=lambda q: [0],
        vector_index=Index(),
        generator=gen,
        classifier=cls,
        event_logger=logger,
        answer_schema={},
        classification_schema=scope_schema(),
        scope_classification=True,
        version_resolver=resolver,
        version_resolution_schema={},
    )
    assert result["answer_label"] == expected_label
    assert result["answer_status"] == expected_status
    assert cls.calls == 2 and resolver.calls == 1 and gen.calls == 1
    assert "version_resolution_observation" in cls.prompts[1]
    assert "元のtarget文字列" in cls.prompts[1]
    assert result["scope_diagnostic"] == initial
    recheck = result["version_resolution"]["revalidation"]
    events = [e[1] for e in logger.events if e[0] == "classification"]
    assert len(events) == 3
    assert events[1]["prompt_version"] == "scope-version-revalidation-v1"
    assert recheck["raw_output"] == (None if mode == "timeout" else checked)
    if mode != "timeout":
        assert recheck["input_tokens"] == 11 and recheck["output_tokens"] == 7
    if mode in {"keep_case", "keep_policy"}:
        assert "元の確認事項" in result["answer"]
    if expected_status != "SUCCESS":
        assert result["claims"] == [] and "500円" not in result["answer"]
