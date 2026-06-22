from src.document_loader import load_markdown_documents
from src.chunking import split_documents
from src.vector_store import create_vector_store


def main() -> None:
    """
    docs/ 配下のMarkdown文書を読み込み、
    チャンク分割してChromaへ登録する。
    """

    documents = load_markdown_documents()
    print(f"読み込んだ文書数: {len(documents)}")

    chunks = split_documents(documents)
    print(f"作成したチャンク数: {len(chunks)}")

    create_vector_store(chunks, reset_db=True)
    print("Chromaへの登録が完了しました。")


if __name__ == "__main__":
    main()