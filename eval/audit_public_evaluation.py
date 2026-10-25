"""Check published aggregate arithmetic without API calls or private artifacts.

This is a new audit utility, not a reconstruction of the original generation or
judge runners. Missing case records cannot be recovered from aggregate counts.
The two limited corrections below transcribe already published review decisions;
they do not re-score answers or complete a same-rubric model comparison.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "integration": "eval/results/autoresearch/freeform-integration-regression-20261024-01/scorecard.json",
    "integration_manifest": "eval/results/autoresearch/freeform-integration-regression-20261024-01/run_manifest.json",
    "challenge": "eval/results/autoresearch/challenge-freeform-20261024-01/scorecard.json",
    "challenge_manifest": "eval/results/autoresearch/challenge-freeform-20261024-01/run_manifest.json",
    "challenge_review": "eval/results/autoresearch/challenge-freeform-20261024-01/human_review_adjudication.md",
    "model_manifest": "eval/results/model_tier_test_confirmation_20261019/run_manifest.json",
    "model_review": "eval/results/model_tier_test_confirmation_20261019/report.md",
}
PAIR_KEYS = ("candidate_only_success", "baseline_only_success", "both_success", "both_fail")
# The arithmetic corrections are transcribed from these exact historical
# records. If a record changes, review its meaning before updating this audit.
CORRECTION_SOURCE_HASHES = {
    "challenge_review": "95ac38b6a73d7d4d29ecb263f2a2596ab8732237f7c1cc3c0be512709f96499e",
    "model_review": "aa6dde50ba5c9455024d9b60f32c2449ae495122728611a8eb72a4850934e183",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _count(value, name):
    _require(type(value) is int and value >= 0, f"{name}: expected non-negative integer")
    return value


def _equal(actual, expected, name):
    _require(actual == expected, f"{name}: expected {expected!r}, got {actual!r}")


def _rate(value, numerator, denominator, name, tolerance=1e-6):
    _require(denominator > 0, f"{name}: denominator must be positive")
    _require(type(value) in (int, float) and math.isfinite(value), f"{name}: invalid rate")
    _require(abs(value - numerator / denominator) <= tolerance, f"{name}: count/rate mismatch")


def audit_integration(score, manifest):
    count = _count(score["case_count"], "integration.case_count")
    _equal(manifest["case_count"], count, "integration.manifest.case_count")
    pair = {key: _count(score["paired_case_outcomes"][key], key) for key in PAIR_KEYS}
    _equal(sum(pair.values()), count, "integration.paired_total")
    for arm, only in (("candidate", "candidate_only_success"), ("baseline", "baseline_only_success")):
        data = score[arm]
        success = _count(data["answer_success_count"], f"{arm}.success")
        _equal(data["case_count"], count, f"{arm}.case_count")
        _equal(data["answer_success_denominator"], count, f"{arm}.denominator")
        _equal(success, pair["both_success"] + pair[only], f"{arm}.paired_success")
        _rate(data["answer_success_rate"], success, count, f"{arm}.rate")
        ids = score[f"{arm}_only_case_ids"]
        _require(isinstance(ids, list) and all(isinstance(x, str) for x in ids), f"{arm}: invalid case IDs")
        _equal(len(ids), pair[only], f"{arm}.case_ids_count")
        _equal(len(set(ids)), len(ids), f"{arm}.unique_case_ids")
    _require(not set(score["candidate_only_case_ids"]) & set(score["baseline_only_case_ids"]), "overlapping improvement/regression IDs")
    by_dataset = score["paired_case_outcomes"]["by_dataset"]
    _equal(set(by_dataset), set(manifest["dataset_counts"]), "integration.dataset_names")
    totals = dict.fromkeys(PAIR_KEYS, 0)
    for name, data in by_dataset.items():
        mapped = dict(zip(PAIR_KEYS, (data["candidate_only"], data["baseline_only"], data["both_pass"], data["both_fail"])))
        for key, value in mapped.items():
            totals[key] += _count(value, f"{name}.{key}")
        _equal(sum(mapped.values()), manifest["dataset_counts"][name], f"{name}.total")
    _equal(totals, pair, "integration.dataset_pair_totals")
    return {
        "candidate_success": score["candidate"]["answer_success_count"],
        "baseline_success": score["baseline"]["answer_success_count"],
        "denominator": count,
        "paired_case_outcomes": pair,
        "candidate_only_case_ids": score["candidate_only_case_ids"],
        "baseline_only_case_ids": score["baseline_only_case_ids"],
        "case_level_reproduction": False,
        "baseline_route": "unconfirmed: original runner and answer records unavailable",
        "scoring": "published provisional machine composite; no new judging",
    }


def audit_challenge(score, manifest):
    count = _count(manifest["case_count"], "challenge.case_count")
    scenarios = _count(score["scenario_count"], "challenge.scenario_count")
    _equal(manifest["scenario_count"], scenarios, "challenge.scenario_count")
    for arm in ("candidate", "baseline"):
        data = score[arm]
        successes = _count(data["pass_expressions"], f"{arm}.pass")
        failures = _count(data["fail_expressions"], f"{arm}.fail")
        unresolved = _count(data["unresolved_expressions"], f"{arm}.unresolved")
        _equal(successes + failures, data["scored_expressions"], f"{arm}.scored")
        _equal(successes + failures + unresolved, count, f"{arm}.count")
        _rate(data["expression_success_rate"], successes, count, f"{arm}.rate")
    pair = {key: _count(value, key) for key, value in score["paired_scenario_outcomes"].items()}
    _equal(sum(pair.values()), scenarios, "challenge.paired_scenarios")
    # This transcription is valid only for the documented original scorecard.
    # Case-level judgments are not available to independently verify these IDs.
    _equal((count, scenarios), (80, 40), "challenge.documented_correction_scope")
    _equal((score["candidate"]["pass_expressions"], score["baseline"]["pass_expressions"]), (77, 76), "challenge.original_successes")
    _equal(pair, {
        "baseline_only_success": 1, "both_success": 37,
        "candidate_only_success": 1, "neither_complete_success": 1,
        "unresolved_or_incomplete": 0,
    }, "challenge.original_pairs")
    return {
        "machine": {"candidate_success": 77, "baseline_success": 76, "denominator": count, "paired_scenario_outcomes": pair},
        "documented_limited_correction": {
            "candidate_success": score["candidate"]["pass_expressions"] + 2,
            "baseline_success": score["baseline"]["pass_expressions"] + 2,
            "denominator": count,
            "corrected_expression_ids": ["CH-I07-F", "CH-I07-P"],
            "paired_scenario_outcomes": {"candidate_only": 1, "baseline_only": 1, "both": pair["both_success"] + 1, "neither": pair["neither_complete_success"] - 1},
            "source": INPUTS["challenge_review"],
            "reviewer": "user, as recorded in the existing review; no new review",
            "all_expressions_human_rescored": False,
        },
        "case_level_reproduction": False,
        "comparison": "original one-call prompt vs revised one-call prompt, fixed evidence",
    }


def audit_model_confirmation(manifest):
    count = _count(manifest["source"]["case_count"], "model.case_count")
    results = manifest["conditions"]["results_by_model"]
    original = {}
    for model in manifest["conditions"]["models"]:
        data = results[model]
        success = _count(data["overall_success_count"], f"{model}.success")
        a1 = _count(data["A1"]["denominator"], f"{model}.A1")
        a23 = _count(data["A2_A3"]["denominator_for_M4"], f"{model}.A23")
        review = _count(data["review_required"], f"{model}.review_required")
        _equal(a1 + a23 + review, count, f"{model}.denominators")
        _equal(data["overall_success_denominator"], count, f"{model}.overall_denominator")
        _equal(data["G1_denominator"], a1 + a23, f"{model}.G1_denominator")
        _equal(success, data["A1"]["M3_success"] + data["A2_A3"]["M4_appropriate_hold"], f"{model}.M3_plus_M4")
        _rate(data["overall_success_rate"], success, count, f"{model}.rate", tolerance=1e-4)
        _require(0 <= success <= a1 + a23, f"{model}: success exceeds scorable cases")
        original[model] = {"success": success, "denominator": count, "A1_denominator": a1, "A2_A3_denominator": a23, "scorable_denominator": a1 + a23, "review_required": review}
    _equal((count, original["gemini-3.8-flash"]["success"]), (44, 32), "model.documented_correction_scope")
    return {
        "original": original,
        "documented_flash_only_correction": {
            "success": original["gemini-3.8-flash"]["success"] + 3,
            "denominator": count,
            "case_ids": ["X014-T0", "X014-T1", "X026-T0"],
            "source": INPUTS["model_review"],
            "reviewer": "user, as recorded in the existing selection report; no new review",
            "flash_lite_rescored": False,
        },
        "same_rubric_rescoring_complete": False,
        "case_level_reproduction": False,
    }


def build_audit(root=ROOT):
    # The allowlist deliberately excludes holdout predictions, gold and private
    # scoring artifacts. Do not replace this with recursive file discovery.
    payloads = {name: (root / relative).read_bytes() for name, relative in INPUTS.items()}
    for name, expected in CORRECTION_SOURCE_HASHES.items():
        _equal(hashlib.sha256(payloads[name]).hexdigest(), expected, f"{name}.source_hash")
    parsed = {name: json.loads(content) for name, content in payloads.items() if INPUTS[name].endswith(".json")}
    return {
        "schema_version": "1.0",
        "utility_kind": "new offline public aggregate consistency audit",
        "status": "AGGREGATE_CONSISTENT",
        "external_api_calls": 0,
        "case_level_reproduction": False,
        "quality_reassessment": False,
        "source_sha256": {INPUTS[name]: hashlib.sha256(content).hexdigest() for name, content in payloads.items()},
        "integration": audit_integration(parsed["integration"], parsed["integration_manifest"]),
        "challenge": audit_challenge(parsed["challenge"], parsed["challenge_manifest"]),
        "model_confirmation": audit_model_confirmation(parsed["model_manifest"]),
        "limitations": [
            "Original answer records, judge prompts and case-level judgments are missing for these runs.",
            "Documented corrections are applied only to aggregate arithmetic, not independently verified answers.",
            "No holdout files are read; no quality gate or adoption decision is changed.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a new JSON file; refuse to overwrite an existing file")
    args = parser.parse_args(argv)
    try:
        result = build_audit()
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as file:
                file.write(serialized)
        else:
            print(serialized, end="")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Public aggregate audit failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
