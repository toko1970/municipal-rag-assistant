"""Audit frozen inputs and derive a readable paired breakdown; no API calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

from eval.evaluate_classification_scope_policy import score, summarize


def analyze(out):
    manifest = json.loads((out / "manifest.json").read_text())
    for name, digest in manifest["frozen_hashes"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest, name
    cases = json.loads((out / "cases.json").read_text())
    tasks = json.loads((out / "tasks.json").read_text())
    records = [json.loads(line) for line in (out / "records.jsonl").read_text().splitlines()]
    saved = json.loads((out / "summary.json").read_text())
    by_id = {c["id"]: c for c in cases}
    for task, row in zip(tasks, records, strict=False):
        for field in ("case_id", "arm", "repetition", "prompt_sha256"):
            assert row[field] == task[field], (row["index"], field)
        assert hashlib.sha256(task["prompt"].encode()).hexdigest() == row["prompt_sha256"]
        assert json.loads(task["prompt"].split("判定対象: ", 1)[1]) == by_id[row["case_id"]]["payload"]
        if not row.get("error"):
            recalculated = score(by_id[row["case_id"]], row["data"])
            assert all(row[k] == v for k, v in recalculated.items())
    spent = sum(r.get("estimated_accounting_usd", 0) for r in records)
    recomputed = summarize(cases, tasks, records, saved["stop_reason"], spent)
    assert recomputed == saved
    by_key = {(r["case_id"], r["arm"], r["repetition"]): r for r in records}
    details = []
    for case in cases:
        arms = {arm: by_key.get((case["id"], arm, 1), {}) for arm in ("baseline", "candidate")}
        details.append({"case_id": case["id"], "scenario_id": case["scenario_id"], "kind": case["kind"],
                        "expected_label": case["expected_label"],
                        "baseline": {k: arms["baseline"].get(k) for k in ("label", "factors", "correct", "display_error", "error")},
                        "candidate": {k: arms["candidate"].get(k) for k in ("label", "factors", "correct", "display_error", "error")}})
    metrics = {}
    for arm in ("baseline", "candidate"):
        chosen = [r for r in records if r["arm"] == arm]
        known = [r for r in chosen if r["repetition"] == 1 and by_id[r["case_id"]]["kind"] == "known_development"]
        metrics[arm] = {"known_expression_correct": sum(r.get("correct", False) for r in known), "known_expression_total": 20,
                        "calls": len(chosen), "model_versions": dict(Counter(r.get("model_version") for r in chosen)),
                        "input_tokens": sum((r.get("usage") or {}).get("prompt_token_count") or 0 for r in chosen),
                        "output_tokens_including_thought": sum(((r.get("usage") or {}).get("candidates_token_count") or 0) + ((r.get("usage") or {}).get("thoughts_token_count") or 0) for r in chosen),
                        "median_api_latency_s": statistics.median(r["latency_seconds"] for r in chosen) if chosen else None,
                        "estimated_accounting_usd": sum(r.get("estimated_accounting_usd", 0) for r in chosen)}
    repeats = []
    for cid in manifest["repeat_ids"]:
        for arm in ("baseline", "candidate"):
            first = by_key.get((cid, arm, 1), {})
            second = by_key.get((cid, arm, 2), {})
            repeats.append({"case_id": cid, "arm": arm, "both_present": bool(first and second),
                            "factors_identical": bool(first and second) and first.get("factors") == second.get("factors"),
                            "both_correct": bool(first.get("correct") and second.get("correct"))})
    result = {"frozen_payload_and_scores_verified": True,
              "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "summary": recomputed, "metrics": metrics, "case_details": details, "repeats": repeats}
    with (out / "analysis.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": recomputed, "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    analyze(parser.parse_args().output_dir)
