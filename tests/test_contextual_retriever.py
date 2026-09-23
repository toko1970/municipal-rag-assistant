from types import SimpleNamespace
import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from eval.contextual_retriever import (
    chunks_fingerprint,
    contextualize_chunks,
    retrieve_documents_with_score,
)


class ContextualRetrieverTest(unittest.TestCase):
    def test_adds_full_heading_path_without_changing_original_chunk(self):
        original = Document(
            page_content="## 4.2 提出期限\n変更日から10日以内に提出すること。",
            metadata={
                "document_id": "DOC-004",
                "見出し1": "4. 通勤経路変更届",
                "見出し2": "4.2 提出期限",
                "chunk_id": 59,
            },
        )

        contextualized = contextualize_chunks([original])[0]

        self.assertTrue(
            contextualized.page_content.startswith(
                "見出し階層: 4. 通勤経路変更届 > 4.2 提出期限\n\n"
            )
        )
        self.assertEqual(
            contextualized.metadata["contextual_heading"],
            "4. 通勤経路変更届 > 4.2 提出期限",
        )
        self.assertFalse(original.page_content.startswith("見出し階層:"))
        self.assertNotIn("contextual_heading", original.metadata)

    def test_fingerprint_changes_with_context(self):
        first = Document(page_content="本文A", metadata={"document_id": "DOC-001"})
        second = Document(page_content="本文B", metadata={"document_id": "DOC-001"})

        self.assertNotEqual(
            chunks_fingerprint([first]),
            chunks_fingerprint([second]),
        )

    def test_retrieves_requested_number_of_chunks(self):
        expected = [(SimpleNamespace(metadata={"chunk_id": 1}), 0.1)]
        store = SimpleNamespace(
            similarity_search_with_score=lambda **kwargs: (
                expected if kwargs == {"query": "提出期限", "k": 3} else []
            )
        )

        with patch(
            "eval.contextual_retriever.get_contextual_vector_store",
            return_value=store,
        ):
            results = retrieve_documents_with_score("提出期限", top_k=3)

        self.assertEqual(results, expected)


if __name__ == "__main__":
    unittest.main()
