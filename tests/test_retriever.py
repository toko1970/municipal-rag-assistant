from types import SimpleNamespace
import unittest
from unittest.mock import patch

from eval.hybrid_retriever import retrieve_documents_with_score


class HybridRetrieverTest(unittest.TestCase):
    def test_reranks_candidates_and_preserves_vector_distance(self):
        candidates = [
            (SimpleNamespace(metadata={"chunk_id": index}), float(index) / 10)
            for index in range(1, 5)
        ]
        store = SimpleNamespace(
            similarity_search_with_score=lambda **_kwargs: candidates
        )

        with patch("eval.hybrid_retriever.get_vector_store", return_value=store):
            with patch(
                "eval.hybrid_retriever.lexical_scores",
                return_value=[0.0, 0.0, 1.0, 0.0],
            ):
                results = retrieve_documents_with_score("支給条件", top_k=2)

        self.assertEqual([doc.metadata["chunk_id"] for doc, _ in results], [1, 3])
        self.assertEqual([score for _, score in results], [0.1, 0.3])


if __name__ == "__main__":
    unittest.main()
