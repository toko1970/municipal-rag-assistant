from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_core.documents import Document

from config import CHUNK_SIZE, CHUNK_OVERLAP


def split_documents(documents: list[Document]) -> list[Document]:
    """
    Markdown文書を見出し構造を考慮してチャンク分割する。
    """

    headers_to_split_on = [
        ("#", "見出し1"),
        ("##", "見出し2"),
        ("###", "見出し3"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )

    header_chunks = []

    for document in documents:
        split_docs = markdown_splitter.split_text(document.page_content)

        for split_doc in split_docs:
            merged_metadata = {
                **document.metadata,
                **split_doc.metadata,
            }

            header_chunks.append(
                Document(
                    page_content=split_doc.page_content,
                    metadata=merged_metadata,
                )
            )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=[
            "\n\n",
            "\n",
            "。",
            "、",
            "",
        ],
    )

    chunks = text_splitter.split_documents(header_chunks)

    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = idx

    return chunks


# if __name__ == "__main__":
#     from src.document_loader import load_markdown_documents

#     docs = load_markdown_documents()
#     chunks = split_documents(docs)

#     print(f"元文書数: {len(docs)}")
#     print(f"チャンク数: {len(chunks)}")

#     for chunk in chunks[:5]:
#         print("-" * 40)
#         print(chunk.metadata)
#         print(chunk.page_content[:300])