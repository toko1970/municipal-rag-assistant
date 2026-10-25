"""Pure, deterministic checks for the two public RAG v2 return contracts.

These checks detect broken output and missing retrieved evidence. They do not
judge the meaning of free-form answers or turn an offline No-go into acceptance.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5


LABELS = ("根拠十分", "判断要", "文書不足")
INCOMPLETE_FINISH_REASONS = frozenset({
    "MAX_TOKENS", "LENGTH", "SAFETY", "RECITATION", "BLOCKLIST",
    "PROHIBITED_CONTENT", "SPII",
})


@dataclass(frozen=True)
class EvidenceExpectation:
    document_key: str
    headings: tuple[str, ...] = ()
    visual_required: bool = False

    def matches(self, reference: Mapping) -> bool:
        # The candidate returns the key, whereas the structured flow returns
        # uuid5(document:key). Both are existing ingestion/serialization contracts.
        identities = {
            self.document_key,
            str(uuid5(NAMESPACE_URL, f"document:{self.document_key}")),
        }
        document_id = reference.get("document_id")
        if not isinstance(document_id, str) or document_id not in identities:
            return False
        if self.headings and reference.get("heading") not in self.headings:
            return False
        content = reference.get("content")
        if not isinstance(content, str) or not content.strip():
            return False
        if self.visual_required:
            asset = reference.get("visual_asset")
            if not isinstance(asset, Mapping):
                return False
            if not isinstance(asset.get("content"), bytes) or not asset["content"]:
                return False
            if asset.get("mime_type") not in ("image/png", "image/jpeg", "image/webp"):
                return False
            if type(asset.get("page_number")) is not int or asset["page_number"] < 1:
                return False
        return True


@dataclass(frozen=True)
class SmokeCase:
    case_id: str
    question: str
    expected_labels: tuple[str, ...]
    required_evidence: tuple[EvidenceExpectation, ...]
    sources: tuple[str, ...]
    semantic_checks: tuple[str, ...]


SMOKE_CASES = (
    SmokeCase(
        "salary_day",
        "給与支給日はいつですか？",
        ("根拠十分",),
        (EvidenceExpectation("DOC-001", ("3. 給与支給日",)),),
        ("docs/01_salary_rules.md#3-給与支給日",),
        ("毎月21日、土日祝の場合は直前営業日と説明し、別の支給日を補わない。",),
    ),
    SmokeCase(
        "missing_document",
        "退職手当の具体的な計算式を教えてください。",
        ("文書不足",),
        (),
        ("docs/01_salary_rules.md", "docs/02_allowance_notice.md",
         "docs/03_hr_faq.md", "docs/04_procedure_manual.md", "docs/05_revision_notice.md"),
        ("取得根拠に計算式がないことを説明し、一般的な計算式を作らない。",
         "不足する規程・所管部署など、次に確認する対象を示す。"),
    ),
    SmokeCase(
        "missing_case_facts",
        "住居手当を受け取れますか？契約名義、家賃額、住居届の提出状況はまだ確認できていません。",
        ("判断要",),
        (EvidenceExpectation("DOC-002", ("3.2 支給要件",)),),
        ("docs/02_allowance_notice.md#32-支給要件",),
        ("本人名義、家賃額、届出状況の確認を求め、個別の支給可否を断定しない。",),
    ),
    SmokeCase(
        "visual_table",
        "通勤手当 支給額・区分表で、常勤職員が月15日以上通勤する場合の月額はいくらですか？",
        ("根拠十分",),
        (EvidenceExpectation("visual-demo-table_dev_001", visual_required=True),),
        ("eval/visual_fixtures/documents/table_dev_001.pdf",
         "eval/visual_fixtures/gold/table_dev_001.json"),
        ("常勤職員・月15日以上の行を対応させ、12,000円が上限額であることも説明する。",
         "実UIで当該表のページ画像と回答の対応を確認する。"),
    ),
    SmokeCase(
        "missing_counting_rule",
        "2026年10月1日に住所を変更しました。住所変更届の提出期限を具体的な年月日で教えてください。初日算入・不算入の規則は確認できていません。",
        # The legacy v1 deadline contract uses 判断要; Rubric v2 distinguishes
        # missing rules as 文書不足. This smoke blocks a sufficient classification,
        # without rewriting either rubric or claiming label-quality equivalence.
        ("判断要", "文書不足"),
        (EvidenceExpectation("DOC-004", ("2.2 提出期限",)),),
        ("docs/04_procedure_manual.md#22-提出期限",
         "tests/test_query_service.py::test_deadline_without_explicit_counting_rule_falls_back_safely",
         "design/CLASSIFICATION_RUBRIC_V2.md#23-文書不足"),
        ("文書の14日以内という規定と、未確認の初日算入・不算入を区別する。",
         "起算規則や具体期限日を推測で確定せず、確認すべき規則を説明する。"),
    ),
)


@dataclass(frozen=True)
class SmokeVerdict:
    passed: bool
    failure_kind: str | None
    reasons: tuple[str, ...]
    matched_evidence: tuple[str, ...] = ()
    semantic_review_status: str = "PENDING"


def _has_substantive_body(text: str) -> bool:
    """Accept legacy hold guidance without a 回答 heading, not label-only text."""
    body = []
    for raw_line in text.splitlines():
        line = raw_line.strip().replace("**", "")
        if line.startswith(("根拠文書:", "根拠文書：")):
            break
        if line.startswith(("回答分類:", "回答分類：")):
            continue
        if line.strip("（）() ") in LABELS:
            continue
        if line.startswith(("回答:", "回答：")):
            line = line[3:].strip()
        # Separators, empty bullets, quotes and code fences are presentation,
        # not an answer. Unicode letters/digits retain Japanese, English and
        # numeric answers without making a claim about their semantic quality.
        if any(character.isalnum() for character in line):
            body.append(line)
    return bool(body)


def validate_smoke_result(result: object, case: SmokeCase) -> SmokeVerdict:
    """Validate a returned result without I/O, mutation or an LLM judge.

    `answer_status` is the actual common field of query_service(v2) and
    simple_rag_flow. We do not read a fictitious generic `status` field, require
    claims/classification from the one-call flow, or require finish_reason from
    the structured flow (which does not expose it).
    """
    def fail(kind: str, reason: str) -> SmokeVerdict:
        return SmokeVerdict(False, kind, (reason,))

    if not isinstance(result, Mapping):
        return fail("FORMAT_ERROR", "回答結果がobjectではありません。")
    status = result.get("answer_status")
    if not isinstance(status, str) or not status:
        return fail("FORMAT_ERROR", "answer_statusがありません。")
    if status == "PROVIDER_ERROR":
        return fail("PROVIDER_ERROR", "provider失敗が返されました。")
    if status == "GENERATION_INCOMPLETE":
        return fail("GENERATION_INCOMPLETE", "回答の生成が完了していません。")
    if status != "SUCCESS":
        return fail("PIPELINE_FAILURE", "回答処理がSUCCESSではありません。")
    if result.get("degraded", False) is not False:
        return fail("PIPELINE_FAILURE", "回答がdegraded状態です。")
    generation = result.get("generation", {})
    if not isinstance(generation, Mapping):
        return fail("FORMAT_ERROR", "generation metadataがobjectではありません。")
    finish_reason = str(generation.get("finish_reason") or "").upper()
    if finish_reason in INCOMPLETE_FINISH_REASONS:
        return fail("GENERATION_INCOMPLETE", "token打切りまたは生成ブロックを検出しました。")
    label = result.get("answer_label")
    if label not in LABELS:
        return fail("FORMAT_ERROR", "回答分類が欠落または不正です。")
    answer = result.get("answer")
    if not isinstance(answer, str) or not _has_substantive_body(answer):
        return fail("FORMAT_ERROR", "回答本文または保留の説明がありません。")
    if label not in case.expected_labels:
        return fail("EXPECTATION_MISMATCH", "このケースで許容する回答分類と一致しません。")
    references = result.get("references")
    if not isinstance(references, list) or any(not isinstance(ref, Mapping) for ref in references):
        return fail("FORMAT_ERROR", "referencesがobjectの配列ではありません。")
    matched = []
    for expected in case.required_evidence:
        if not any(expected.matches(ref) for ref in references):
            return fail("MISSING_REFERENCE", "必要な文書・節・本文または図表画像を取得できていません。")
        matched.append(expected.document_key)
    return SmokeVerdict(True, None, (), tuple(matched))
