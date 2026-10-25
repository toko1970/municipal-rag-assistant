from __future__ import annotations

import unittest

from eval.score_freeform_paired_relative import (
    aggregate_paired_results,
    compute_custodian_gold_metrics,
)


def _fixture():
    predictions = []
    review_map = []
    system_key = {"run_id": "r", "pairs": []}
    judgments = []
    gold = {"scenarios": []}
    for index in range(1, 4):
        pair_id = f"pair-{index}"
        review_id = f"blind-{index}"
        scenario_id = f"TH{index:03d}"
        predictions.append(
            {
                "pair_id": pair_id,
                "scenario_id": scenario_id,
                "variant_type": "formal",
                "left": {"status": "SUCCESS"},
                "right": {"status": "SUCCESS"},
                "retrieved_references": [{"document_id": "DOC-1"}],
            }
        )
        review_map.append(
            {
                "review_id": review_id,
                "pair_id": pair_id,
                "scenario_id": scenario_id,
                "variant_type": "formal",
            }
        )
        system_key["pairs"].append(
            {
                "pair_id": pair_id,
                "left_system": "incumbent",
                "right_system": "candidate",
            }
        )
        judgments.append(
            {
                "review_id": review_id,
                "pair_status": "RESOLVED",
                "unresolved_attribution": None,
                "left": {
                    "unsupported_assertion": index == 1,
                    "g1": 0,
                    "observed_decision": "ANSWER",
                    "content_accuracy": "PASS",
                },
                "right": {
                    "unsupported_assertion": False,
                    "g1": 0,
                    "observed_decision": "ANSWER",
                    "content_accuracy": "PASS",
                },
            }
        )
        gold["scenarios"].append(
            {
                "scenario_id": scenario_id,
                "expected_classification": "grounded",
                "expected_corpus_answerability": True,
                "expected_document_ids": ["DOC-1"],
            }
        )
    return predictions, review_map, system_key, judgments, gold


class PairedScoringTests(unittest.TestCase):
    def test_gold_computable_retrieval_metrics_exclude_unanswerable_cases(self):
        predictions, _review_map, _system_key, _judgments, gold = _fixture()
        gold["scenarios"][2]["expected_classification"] = "insufficient_documents"
        gold["scenarios"][2]["expected_corpus_answerability"] = False
        gold["scenarios"][2]["expected_document_ids"] = []
        result = compute_custodian_gold_metrics(predictions, gold)
        self.assertEqual(result["gold_classification_counts"]["insufficient_documents"], 1)
        self.assertEqual(result["retrieval_document_hit_at_8"]["all_required_documents"]["denominator"], 2)
        self.assertEqual(result["retrieval_document_hit_at_8"]["all_required_documents"]["numerator"], 2)

    def test_pair_unresolved_excludes_both_and_errors_are_separate(self):
        predictions, review_map, system_key, judgments, gold = _fixture()
        judgments[1] = {
            "review_id": "blind-2",
            "pair_status": "UNRESOLVED",
            "unresolved_attribution": "RIGHT",
            "left": {
                "unsupported_assertion": False,
                "g1": 0,
                "observed_decision": "ANSWER",
                "content_accuracy": "PASS",
            },
            "right": {
                "unsupported_assertion": None,
                "g1": "UNRESOLVED",
                "observed_decision": "HOLD",
                "content_accuracy": "UNRESOLVED",
            },
        }
        predictions[2]["right"]["status"] = "API_ERROR"
        judgments[2] = {
            "review_id": "blind-3",
            "pair_status": "OPERATIONAL_ERROR",
            "unresolved_attribution": None,
            "left": {},
            "right": {},
        }

        result = aggregate_paired_results(
            predictions,
            review_map,
            system_key,
            judgments,
            gold,
            bootstrap_replicates=100,
            seed=20261024,
        )

        self.assertEqual(result["primary"]["denominator"], 1)
        self.assertEqual(result["primary"]["incumbent"]["numerator"], 1)
        self.assertEqual(result["primary"]["candidate"]["numerator"], 0)
        self.assertEqual(result["unresolved"]["pair_count"], 1)
        self.assertEqual(result["unresolved"]["candidate_attributed_count"], 1)
        self.assertEqual(result["operations"]["error_pair_count"], 1)
        self.assertEqual(result["operations"]["errors_by_system"]["candidate"], 1)

    def test_duplicate_pair_is_rejected_before_aggregation(self):
        predictions, review_map, system_key, judgments, gold = _fixture()
        predictions.append(dict(predictions[0]))
        with self.assertRaisesRegex(ValueError, "duplicate prediction pair"):
            aggregate_paired_results(
                predictions, review_map, system_key, judgments, gold,
                bootstrap_replicates=10, seed=20261024,
            )

    def test_bootstrap_is_deterministic_and_g1_zero_increment_is_enforced(self):
        predictions, review_map, system_key, judgments, gold = _fixture()
        judgments[0]["right"]["g1"] = 1
        first = aggregate_paired_results(
            predictions, review_map, system_key, judgments, gold,
            bootstrap_replicates=200, seed=20261024,
        )
        second = aggregate_paired_results(
            predictions, review_map, system_key, judgments, gold,
            bootstrap_replicates=200, seed=20261024,
        )
        self.assertEqual(first["primary"]["bootstrap_95_percentile"], second["primary"]["bootstrap_95_percentile"])
        self.assertEqual(first["g1"]["candidate_only_count"], 1)
        self.assertEqual(first["g1"]["gate_status"], "FAIL")

    def test_duplicate_review_is_rejected(self):
        predictions, review_map, system_key, judgments, gold = _fixture()
        judgments.append(dict(judgments[0]))
        with self.assertRaisesRegex(ValueError, "duplicate review"):
            aggregate_paired_results(
                predictions, review_map, system_key, judgments, gold,
                bootstrap_replicates=10, seed=20261024,
            )


if __name__ == "__main__":
    unittest.main()
