from pathlib import Path

from src.ingestion import EMBEDDING_PROFILE_KEY, build_markdown_elements, ingest_markdown_documents


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


def test_ingestion_embeds_context_but_indexes_original_content(tmp_path: Path) -> None:
    path = tmp_path / "notice.md"
    write_document(path, "給与は毎月21日に支給します。")

    class Repository:
        def __init__(self) -> None:
            self.profile = None
            self.statuses = []

        def upsert_markdown_elements(self, **_kwargs) -> None:
            pass

        def upsert_embedding_profile(self, **kwargs) -> None:
            self.profile = kwargs

        def mark_index_status(self, element_ids, status) -> None:
            self.statuses.append((element_ids, status))

    class Embeddings:
        def __init__(self) -> None:
            self.texts = []
            self.task_type = None

        def embed_documents(self, texts, *, task_type):
            self.texts = texts
            self.task_type = task_type
            return [[1.0, 0.0, 0.0] for _text in texts]

    class Index:
        def __init__(self) -> None:
            self.elements = []
            self.profile = None

        def ensure_collection(self, _dimensions) -> None:
            pass

        def upsert(self, elements, _vectors, profile) -> None:
            self.elements = elements
            self.profile = profile

    repository = Repository()
    embeddings = Embeddings()
    index = Index()

    result = ingest_markdown_documents(
        repository, index, docs_dir=tmp_path, embeddings=embeddings
    )

    assert result == {"documents": 1, "elements": 1}
    assert embeddings.task_type == "RETRIEVAL_DOCUMENT"
    assert embeddings.texts[0].startswith(
        "文書: テスト通知\n見出し: 通知 > 支給日\n\n"
    )
    assert embeddings.texts[0].endswith(index.elements[0].content)
    assert not index.elements[0].content.startswith("文書: テスト通知")
    assert index.profile == EMBEDDING_PROFILE_KEY
    assert repository.profile["configuration"] == {
        "task_type": "RETRIEVAL_DOCUMENT",
        "document_representation": "contextual-heading-v1",
    }
    assert repository.statuses[-1][1] == "INDEXED"
