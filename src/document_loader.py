from pathlib import Path
import yaml

from datetime import date, datetime

from langchain_core.documents import Document

from config import DOCS_DIR

def normalize_metadata(metadata: dict) -> dict:
    """
    Chromaに保存できる形式へmetadataを変換する。
    """

    normalized = {}

    for key, value in metadata.items():
        if isinstance(value, (date, datetime)):
            normalized[key] = value.isoformat()
        else:
            normalized[key] = value

    return normalized

def parse_markdown_with_metadata(file_path: Path) -> tuple[dict, str]:
    """
    Markdownファイルを読み込み、
    YAML Front Matter のメタデータと本文を分離する。
    """

    text = file_path.read_text(encoding="utf-8")

    if text.startswith("---"):
        parts = text.split("---", 2)

        if len(parts) == 3:
            metadata_text = parts[1]
            body = parts[2].strip()

            metadata = yaml.safe_load(metadata_text) or {}
        else:
            metadata = {}
            body = text
    else:
        metadata = {}
        body = text

    metadata["source"] = file_path.name
    metadata["file_path"] = str(file_path)

    metadata = normalize_metadata(metadata)

    return metadata, body


def load_markdown_documents(docs_dir: Path = DOCS_DIR) -> list[Document]:
    """
    docs/ 配下の Markdown ファイルを読み込み、
    LangChain の Document 形式に変換する。
    """

    documents = []

    markdown_files = sorted(docs_dir.glob("*.md"))

    for file_path in markdown_files:
        metadata, body = parse_markdown_with_metadata(file_path)

        document = Document(
            page_content=body,
            metadata=metadata,
        )

        documents.append(document)

    return documents