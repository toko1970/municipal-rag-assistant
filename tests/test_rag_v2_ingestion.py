from pathlib import Path

from src.ingestion import build_markdown_elements


def write_document(path: Path, body: str) -> None:
    path.write_text(
        "---\n"
        "document_id: test-document\n"
        "document_name: テスト通知\n"
        "---\n"
        f"# 通知\n\n## 支給日\n\n{body}\n",
        encoding="utf-8",
    )


def test_markdown_ids_are_stable_for_same_content(tmp_path: Path) -> None:
    path = tmp_path / "notice.md"
    write_document(path, "給与は毎月21日に支給します。")

    first = build_markdown_elements(path)
    second = build_markdown_elements(path)

    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].document_id == second[0].document_id
    assert first[0].version_id == second[0].version_id


def test_content_change_creates_new_version_but_keeps_document_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notice.md"
    write_document(path, "給与は毎月21日に支給します。")
    first = build_markdown_elements(path)

    write_document(path, "給与は毎月22日に支給します。")
    second = build_markdown_elements(path)

    assert first[0].document_id == second[0].document_id
    assert first[0].version_id != second[0].version_id
    assert first[0].id != second[0].id
