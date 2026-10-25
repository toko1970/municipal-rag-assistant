"""Offline checks for public aggregates; these do not score model answers."""

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from eval.audit_public_evaluation import (
    INPUTS,
    audit_challenge,
    audit_integration,
    audit_model_confirmation,
    build_audit,
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval/results"


def read_result(relative):
    return json.loads((RESULTS / relative).read_text(encoding="utf-8"))


class PublicEvaluationAuditTest(unittest.TestCase):
    def setUp(self):
        self.integration = read_result(
            "autoresearch/freeform-integration-regression-20261024-01/scorecard.json"
        )
        self.integration_manifest = read_result(
            "autoresearch/freeform-integration-regression-20261024-01/run_manifest.json"
        )
        self.challenge = read_result(
            "autoresearch/challenge-freeform-20261024-01/scorecard.json"
        )
        self.challenge_manifest = read_result(
            "autoresearch/challenge-freeform-20261024-01/run_manifest.json"
        )
        self.model_manifest = read_result(
            "model_tier_test_confirmation_20261019/run_manifest.json"
        )

    def test_public_integration_pair_counts_match_both_success_totals(self):
        result = audit_integration(self.integration, self.integration_manifest)
        self.assertEqual(result["candidate_success"], 129)
        self.assertEqual(result["baseline_success"], 125)
        self.assertEqual(result["paired_case_outcomes"]["candidate_only_success"], 4)
        self.assertFalse(result["case_level_reproduction"])

    def test_inconsistent_pair_total_is_rejected(self):
        self.integration["paired_case_outcomes"]["both_success"] = 124
        with self.assertRaises(ValueError):
            audit_integration(self.integration, self.integration_manifest)

    def test_wrong_denominator_is_not_silently_dropped(self):
        self.integration["candidate"]["answer_success_denominator"] = 129
        with self.assertRaises(ValueError):
            audit_integration(self.integration, self.integration_manifest)

    def test_duplicate_improvement_case_id_is_rejected(self):
        self.integration["candidate_only_case_ids"][1] = "VD014"
        with self.assertRaises(ValueError):
            audit_integration(self.integration, self.integration_manifest)

    def test_dataset_pair_counts_must_match_global_counts(self):
        self.integration["paired_case_outcomes"]["by_dataset"][
            "visual_development_30"
        ]["candidate_only"] = 3
        with self.assertRaises(ValueError):
            audit_integration(self.integration, self.integration_manifest)

    def test_invalid_success_types_and_rates_are_rejected(self):
        for invalid in (True, -1, 130.0, "129"):
            with self.subTest(invalid=invalid):
                score = deepcopy(self.integration)
                score["candidate"]["answer_success_count"] = invalid
                with self.assertRaises(ValueError):
                    audit_integration(score, self.integration_manifest)
        self.integration["candidate"]["answer_success_rate"] = 1.0
        with self.assertRaises(ValueError):
            audit_integration(self.integration, self.integration_manifest)

    def test_challenge_keeps_machine_and_limited_correction_separate(self):
        result = audit_challenge(self.challenge, self.challenge_manifest)
        self.assertEqual(result["machine"]["candidate_success"], 77)
        self.assertEqual(result["machine"]["baseline_success"], 76)
        self.assertEqual(result["documented_limited_correction"]["candidate_success"], 79)
        self.assertEqual(result["documented_limited_correction"]["baseline_success"], 78)
        self.assertEqual(
            result["documented_limited_correction"]["paired_scenario_outcomes"],
            {"candidate_only": 1, "baseline_only": 1, "both": 38, "neither": 0},
        )
        self.assertFalse(result["case_level_reproduction"])

    def test_challenge_correction_requires_its_original_aggregate(self):
        # Applying the same +2 again to an already corrected source is unsafe.
        self.challenge["candidate"]["pass_expressions"] = 79
        self.challenge["candidate"]["fail_expressions"] = 1
        self.challenge["candidate"]["expression_success_rate"] = 0.9875
        with self.assertRaises(ValueError):
            audit_challenge(self.challenge, self.challenge_manifest)

    def test_model_comparison_preserves_unresolved_outputs_in_total(self):
        result = audit_model_confirmation(self.model_manifest)
        flash = result["original"]["gemini-3.8-flash"]
        self.assertEqual(flash["success"], 32)
        self.assertEqual(flash["denominator"], 44)
        self.assertEqual(flash["scorable_denominator"], 42)
        self.assertEqual(flash["review_required"], 2)
        self.assertEqual(result["documented_flash_only_correction"]["success"], 35)
        self.assertFalse(result["same_rubric_rescoring_complete"])

    def test_model_count_inconsistency_is_rejected(self):
        results = self.model_manifest["conditions"]["results_by_model"]
        results["gemini-3.8-flash"]["review_required"] = 0
        with self.assertRaises(ValueError):
            audit_model_confirmation(self.model_manifest)

    def test_audit_reads_only_named_public_artifacts(self):
        result = build_audit(ROOT)
        self.assertEqual(result["status"], "AGGREGATE_CONSISTENT")
        self.assertEqual(result["external_api_calls"], 0)
        self.assertFalse(result["case_level_reproduction"])
        for name, digest in result["source_sha256"].items():
            self.assertNotIn("custodian", name)
            self.assertNotIn("paired-relative", name)
            self.assertNotIn("holdout", name)
            self.assertEqual(len(digest), 64)

    def test_changed_correction_source_requires_review(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in INPUTS.values():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            (root / INPUTS["challenge_review"]).write_text("Changed review", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_hash"):
                build_audit(root)

    def test_cli_output_is_new_file_and_existing_output_is_preserved(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            command = [sys.executable, "-m", "eval.audit_public_evaluation", "--output", str(output)]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
