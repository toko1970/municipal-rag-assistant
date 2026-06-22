from src.retriever import retrieve_documents_with_score


TEST_QUERIES = [
    "給与支給日はいつですか？",
    "通勤手当の支給要件は？",
    "住所変更した場合の手続きは？",
    "扶養手当の認定要件は？",
    "給与口座を変更したい",
]


def main() -> None:

    for query in TEST_QUERIES:

        print("\n" + "=" * 80)
        print(f"質問: {query}")
        print("=" * 80)

        results = retrieve_documents_with_score(query)

        for rank, (doc, score) in enumerate(results, start=1):

            print(f"\n順位: {rank}")
            print(f"スコア: {score:.4f}")

            print(
                f"文書: {doc.metadata.get('document_name', 'N/A')}"
            )

            print(
                f"見出し: {doc.metadata.get('見出し2', 'N/A')}"
            )

            print(
                f"チャンクID: {doc.metadata.get('chunk_id', 'N/A')}"
            )

            print("内容:")
            print(doc.page_content[:200])


if __name__ == "__main__":
    main()