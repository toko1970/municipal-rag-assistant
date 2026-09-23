import unittest
from unittest.mock import patch

from eval.contextual_answer import (
    generate_contextual_answer,
    retrieve_documents_with_score,
)


class ContextualAnswerTest(unittest.TestCase):
    @patch("eval.contextual_answer.generate_answer")
    def test_uses_contextual_retriever_without_writing_app_log(self, generate_answer):
        generate_answer.return_value = {"answer": "回答"}

        result = generate_contextual_answer("提出期限は？")

        self.assertEqual(result, {"answer": "回答"})
        generate_answer.assert_called_once()
        kwargs = generate_answer.call_args.kwargs
        self.assertEqual(generate_answer.call_args.args, ("提出期限は？",))
        self.assertIs(kwargs["retrieve_fn"], retrieve_documents_with_score)
        self.assertFalse(kwargs["record_log"])

if __name__ == "__main__":
    unittest.main()
