from types import SimpleNamespace
from uuid import UUID

from src.contracts import SearchHit
from src.temporal_evidence import (
    analyze_temporal_evidence,
    build_temporal_generation_prompt,
    extract_question_date,
    temporal_prompt_instruction,
)


def _hit(
    value: int,
    *,
    heading1: str,
    heading2: str,
    effective_date: str,
    role: str,
    content: str,
) -> SearchHit:
    element = SimpleNamespace(
        id=UUID(int=value),
        document_id=UUID(int=100 + value),
        document_name="テスト文書",
        heading=f"{heading1} > {heading2}",
        content=content,
        page_number=None,
        element_type="text",
        metadata={
            "見出し1": heading1,
            "見出し2": heading2,
            "effective_date": effective_date,
            "document_role": role,
        },
    )
    return SearchHit(element=element, score=1.0, rank=value)


def test_extracts_month_as_first_day() -> None:
    assert extract_question_date("2025年10月の出生") is not None
    assert extract_question_date("日付なし") is None


def test_marks_applicable_revision_and_older_conflicting_source() -> None:
    old = _hit(
        1,
        heading1="扶養手当に関するFAQ",
        heading2="回答",
        effective_date="2025-04-01",
        role="primary",
        content="翌月から支給する。",
    )
    revised = _hit(
        2,
        heading1="5. 扶養手当の改正",
        heading2="改正後",
        effective_date="2025-10-01",
        role="revision_history",
        content="認定月から支給する。",
    )
    transition = _hit(
        3,
        heading1="5. 扶養手当の改正",
        heading2="経過措置",
        effective_date="2025-10-01",
        role="revision_history",
        content="2025年10月1日以降に適用する。",
    )
    procedure = _hit(
        4,
        heading1="3. 扶養親族変更届",
        heading2="3.2 提出期限",
        effective_date="2025-04-01",
        role="primary",
        content="15日以内に提出する。",
    )

    result = analyze_temporal_evidence(
        "2025年10月の出生について支給開始時期と届出期限を教えてください。",
        [old, revised, transition, procedure],
    )

    assert result is not None
    assert result.applicable_domains == ("扶養手当",)
    assert result.applicable_revision_element_ids == (
        str(revised.element.id),
        str(transition.element.id),
    )
    assert result.older_conflicting_element_ids == (str(old.element.id),)
    instruction = temporal_prompt_instruction(
        "2025年10月の出生について支給開始時期と届出期限を教えてください。",
        [old, revised, transition, procedure],
    )
    assert "旧記載候補" in instruction
    assert str(procedure.element.id) not in instruction


def test_comparison_keeps_both_versions() -> None:
    before = _hit(
        1,
        heading1="5. 扶養手当の改正",
        heading2="改正前",
        effective_date="2025-10-01",
        role="revision_history",
        content="翌月から支給する。",
    )
    after = _hit(
        2,
        heading1="5. 扶養手当の改正",
        heading2="改正後",
        effective_date="2025-10-01",
        role="revision_history",
        content="認定月から支給する。",
    )
    unrelated = _hit(
        3,
        heading1="4. 住居手当の改正",
        heading2="改正後",
        effective_date="2025-10-01",
        role="revision_history",
        content="家賃基準を変更する。",
    )

    result = analyze_temporal_evidence(
        "扶養手当の支給開始時期は改正前後でどう変わりましたか？",
        [before, after, unrelated],
    )

    assert result is not None
    assert result.comparison_requested
    assert result.applicable_domains == ("扶養手当",)
    assert str(unrelated.element.id) not in result.applicable_revision_element_ids
    assert result.older_conflicting_element_ids == ()
    assert "両方の記載を保持" in temporal_prompt_instruction(
        "扶養手当の支給開始時期は改正前後でどう変わりましたか？",
        [before, after, unrelated],
    )


def test_prompt_builder_preserves_normal_questions_without_guidance() -> None:
    current = _hit(
        1,
        heading1="給与制度規程",
        heading2="支給日",
        effective_date="2025-04-01",
        role="primary",
        content="毎月21日に支給する。",
    )

    prompt = build_temporal_generation_prompt("給与支給日はいつですか？", [current], {})

    assert not prompt.startswith("版適用情報:")


def test_prompt_builder_prepends_guidance_only_when_applicable() -> None:
    revised = _hit(
        1,
        heading1="4. 住居手当の改正",
        heading2="改正後",
        effective_date="2025-10-01",
        role="revision_history",
        content="住居手当は月額家賃が15,000円を超える場合に対象とする。",
    )

    prompt = build_temporal_generation_prompt(
        "2025年10月以降の住居手当の要件は？", [revised], {}
    )

    assert prompt.startswith("版適用情報:")


def test_housing_facts_map_to_allowance_without_explicit_policy_name() -> None:
    revised = _hit(
        1,
        heading1="4. 住居手当の改正",
        heading2="改正後",
        effective_date="2025-10-01",
        role="revision_history",
        content="月額家賃が15,000円を超える場合に対象とする。",
    )

    instruction = temporal_prompt_instruction(
        "2025年10月に家賃15,500円の住宅へ入居した場合の要件は？",
        [revised],
    )

    assert instruction is not None
    assert "住居手当" in instruction
