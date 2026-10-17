"""Offline recheck of frozen evidence and a fresh service fault-injection run.

No model calls, no changes to previous evidence, and no new holdout claim.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "eval/results/generalization_completion_20261009"
OUT = ROOT / "eval/results/generalization_recheck_20261009"


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def paired(rows, arms, success):
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        groups[row["scenario_id"]][row["arm"]].append(row[success])
    counts = Counter()
    detail = {}
    for sid, values in sorted(groups.items()):
        assert set(values) == set(arms)
        assert all(len(v) == 2 for v in values.values())
        a, b = (all(values[arm]) for arm in arms)
        category = "both" if a and b else "baseline_only" if a else "candidate_only" if b else "neither"
        counts[category] += 1
        detail[sid] = {arms[0]: a, arms[1]: b, "delta": int(b) - int(a)}
    delta = [v["delta"] for v in detail.values()]
    rng = random.Random(20261009)
    bootstrap = sorted(sum(rng.choices(delta, k=len(delta))) / len(delta) for _ in range(20000))
    return {"n_scenarios": len(detail), "paired_counts": dict(counts), "scenarios": detail,
            "net_improvement": sum(delta), "paired_bootstrap_95_percentile_ci": [bootstrap[500], bootstrap[19500]],
            "bootstrap_seed": 20261009, "bootstrap_samples": 20000}


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT / "audit.json").exists():
        raise RuntimeError("Preserve the previous recheck; choose a new output path for a new run")
    inputs = [p for directory in ("deadline", "classification", "display_corrected")
              for p in (BASE / directory).iterdir() if p.is_file()]
    before = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    write("manifest.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
          "scope": "saved-output integrity/reaggregation plus fresh fixed-provider service execution",
          "api_calls_limit": 0, "new_display_runs": 24, "new_display_retries": 0,
          "quality_selection": False, "candidate_changes": False,
          "source_evidence_sha256": before, "runner_sha256": sha(Path(__file__)),
          "rules": "Retain frozen adoption gates. Do not reinterpret existing data as fresh holdout. Compare all 24 display conditions."})

    cm = read(BASE / "classification/manifest.json")
    dm = read(BASE / "deadline/manifest.json")
    checks = {}
    for filename, field in (("challenge.json", "fixture_sha256"), ("frozen_tasks.json", "tasks_sha256"), ("frozen_schema.json", "schema_sha256")):
        checks[f"deadline/{filename}"] = sha(BASE / "deadline" / filename) == dm[field]
    for filename, field in (("challenge.json", "challenge_sha256"), ("corpus.json", "corpus_sha256"), ("frozen_tasks.json", "tasks_sha256")):
        checks[f"classification/{filename}"] = sha(BASE / "classification" / filename) == cm[field]
    for path, expected in cm["source_file_hashes"].items():
        checks[path] = sha(ROOT / path) == expected
    checks["classification_runner"] = sha(ROOT / "eval/run_generalization_classification_20261009.py") == cm["runner_sha256"]
    assert all(checks.values()), checks

    tasks = read(BASE / "deadline/frozen_tasks.json")
    attempts = lines(BASE / "deadline/api_attempts.jsonl")
    reviews = lines(BASE / "deadline/semantic_review.jsonl")
    assert len(tasks) == len(attempts) == len(reviews) == 120
    assert {r["task_index"] for r in reviews} == set(range(120))
    for i, attempt in enumerate(attempts):
        task = tasks[i]
        assert attempt["task_index"] == i and attempt["valid_output"]
        assert hashlib.sha256(task["prompt"].encode()).hexdigest() == task["prompt_sha256"]
        for key in ("id", "scenario_id", "arm", "repetition", "prompt_sha256"):
            assert task[key] == attempt[key]
        assert json.loads(attempt["raw_text"]) == attempt["data"]
    deadline = paired([r for r in reviews if r["repetition"] == 1], ("baseline", "candidate"), "semantic_success")
    assert deadline["paired_counts"] == {"both": 10, "baseline_only": 4, "candidate_only": 6, "neither": 4}

    services = lines(BASE / "classification/service_records.jsonl")
    creviews = lines(BASE / "classification/semantic_review.jsonl")
    capi = lines(BASE / "classification/api_attempts.jsonl")
    assert len(services) == len(creviews) == 88 and len(capi) == 214
    assert {r["index"] for r in services} == {r["index"] for r in creviews} == set(range(88))
    by_index = {r["index"]: r for r in services}
    for row in creviews:
        for key in ("row_id", "scenario_id", "arm", "repetition", "evidence_mode", "status"):
            assert row[key] == by_index[row["index"]][key]
    oracle = [r for r in creviews if r["evidence_mode"] == "oracle" and r["repetition"] == 1]
    classification = paired(oracle, ("v1", "v2"), "manual_final_composite")
    sensitivity = paired([r for r in oracle if r["scenario_id"] not in {"A01", "B01"}], ("v1", "v2"), "manual_final_composite")
    retrieved = paired([r for r in creviews if r["evidence_mode"] == "retrieved"], ("v1", "v2"), "manual_final_composite")
    assert classification["paired_counts"] == {"both": 6, "baseline_only": 2, "candidate_only": 2, "neither": 2}
    assert sensitivity["net_improvement"] == -1 and retrieved["net_improvement"] == -2

    spec = importlib.util.spec_from_file_location("display_recheck", ROOT / "eval/evaluate_display_reliability_completion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    display_tasks = read(BASE / "display_corrected/tasks.json")
    old = read(BASE / "display_corrected/records.json")
    assert len(display_tasks) == len(old) == 24
    fresh = [module.run(task) for task in display_tasks]
    write("display_records.json", fresh)
    # Persisted historical UUIDs are strings; compare the same JSON representation.
    fresh = read(OUT / "display_records.json")
    display_comparison = []
    for task, previous, current in zip(display_tasks, old, fresh):
        assert (task["id"], task["arm"]) == (previous["id"], previous["arm"])
        fields = ("normal_control_pass", "unsafe_claim_visible", "safe_returned_display", "returned", "visible_claim_count", "exception")
        equal = all(previous[k] == current[k] for k in fields)
        for key in ("answer", "answer_label", "status", "claims"):
            equal &= (previous["result"] or {}).get(key) == (current["result"] or {}).get(key)
        display_comparison.append({"id": task["id"], "arm": task["arm"], "matches_prior_behavior": equal})
    assert all(r["matches_prior_behavior"] for r in display_comparison)
    assert all(sha(ROOT / path) == digest for path, digest in before.items())
    write("audit.json", {"completed_at_utc": datetime.now(timezone.utc).isoformat(),
          "checks": checks, "deadline": deadline, "classification_oracle": classification,
          "classification_excluding_ambiguous_gold": sensitivity, "classification_retrieved": retrieved,
          "display_comparison": display_comparison, "display_matching_conditions": 24,
          "new_api_calls": 0, "old_evidence_unchanged": True,
          "semantic_scoring": "Previously reviewed semantic annotations reused; not newly independent annotation",
          "adoption": "Both frozen candidates remain rejected; later adoption gates not executed"})
    print(json.dumps({"deadline": deadline["paired_counts"], "classification": classification["paired_counts"],
                      "display_reproduced": 24, "new_api_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
