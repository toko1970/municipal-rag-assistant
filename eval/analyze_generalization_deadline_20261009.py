"""Offline integrity checks and review sheet for the frozen deadline challenge."""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
import argparse
from pathlib import Path

import jsonschema

DEFAULT_OUT = Path(__file__).resolve().parent / "results/generalization_validation_20261009"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main(out_dir: Path):
    global OUT
    OUT = out_dir.resolve()
    manifest = json.loads((OUT / "manifest.json").read_text())
    assert sha(OUT / "challenge.json") == manifest["fixture_sha256"]
    assert sha(OUT / "frozen_tasks.json") == manifest["tasks_sha256"]
    assert sha(OUT / "frozen_schema.json") == manifest["schema_sha256"]
    tasks = json.loads((OUT / "frozen_tasks.json").read_text())
    fixture = {r["id"]: r for r in json.loads((OUT / "challenge.json").read_text())}
    schema = json.loads((OUT / "frozen_schema.json").read_text())
    records = lines(OUT / "api_records.jsonl")
    assert len(records) <= len(tasks) <= manifest["max_calls"]
    reviews = []
    for i, rec in enumerate(records):
        task = tasks[i]
        assert rec["index"] == i
        assert all(rec[k] == task[k] for k in ("id", "scenario_id", "variant", "arm", "repetition", "prompt_sha256"))
        row = fixture[rec["id"]]
        item = {k: rec[k] for k in ("index", "id", "scenario_id", "variant", "arm", "repetition")}
        item["gold"] = row["gold"]
        item["review_note"] = row["review_note"]
        item["error"] = rec.get("error")
        if "data" in rec:
            try:
                jsonschema.validate(rec["data"], schema)
                item["schema_ok"] = True
            except jsonschema.ValidationError as exc:
                item["schema_ok"] = False
                item["schema_error"] = exc.message
            claims = rec["data"].get("claims", [])
            item["claims"] = [c.get("text", "") for c in claims]
            item["missing_conditions"] = rec["data"].get("missing_conditions", [])
            expected_ids = {e["element_id"] for e in row["evidence"]}
            item["citations_ok"] = bool(claims) and all(
                set(c.get("evidence_element_ids", [])) <= expected_ids
                and bool(c.get("evidence_element_ids")) for c in claims
            )
            joined = "\n".join(item["claims"])
            item["date_string_proxy"] = {
                value: (value in joined or value.replace("-", "/") in joined or
                        f"{int(value[:4])}年{int(value[5:7])}月{int(value[8:10])}日" in joined)
                for value in row["gold"]["required_dates"]
            }
            item["time_string_proxy"] = {
                value: (value in joined or f"{int(value[:2])}時{int(value[3:])}分" in joined
                        or (value.endswith(":00") and f"{int(value[:2])}時" in joined))
                for value in row["gold"]["required_times"]
            }
        reviews.append(item)
    (OUT / "automatic_checks.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reviews))
    summary = {
        "record_count": len(records), "task_count": len(tasks),
        "error_count": sum("error" in r for r in records),
        "schema_invalid": sum(r.get("schema_ok") is False for r in reviews),
        "citation_invalid": sum(r.get("citations_ok") is False for r in reviews),
        "input_tokens": sum((r.get("usage") or {}).get("prompt_token_count") or 0 for r in records),
        "output_tokens": sum(((r.get("usage") or {}).get("candidates_token_count") or 0)
                             + ((r.get("usage") or {}).get("thoughts_token_count") or 0) for r in records),
        "estimated_usd": sum(r.get("estimated_usd", 0) for r in records),
        "latency_p50_s": statistics.median(r["latency_s"] for r in records) if records else None,
        "latency_p95_s": sorted(r["latency_s"] for r in records)[int((len(records)-1)*.95)] if records else None,
        "api_records_sha256": sha(OUT / "api_records.jsonl"),
        "warning": "Date/time string proxy is not semantic scoring; all responses need full-content review.",
    }
    semantic_path = OUT / "semantic_review.jsonl"
    if semantic_path.exists():
        sem = lines(semantic_path)
        assert len(sem) == len(records)
        assert [r["index"] for r in sem] == list(range(len(records)))
        by_pair = defaultdict(dict)
        for rec, review in zip(records, sem):
            assert review["index"] == rec["index"]
            by_pair[(rec["id"], rec["repetition"])][rec["arm"]] = review["semantic_success"]
        complete = {k: v for k, v in by_pair.items() if len(v) == 2 and None not in v.values()}
        pair_counts = {
            "both_pass": sum(v["baseline"] and v["candidate"] for v in complete.values()),
            "baseline_only": sum(v["baseline"] and not v["candidate"] for v in complete.values()),
            "candidate_only": sum(not v["baseline"] and v["candidate"] for v in complete.values()),
            "both_fail": sum(not v["baseline"] and not v["candidate"] for v in complete.values()),
        }
        scenarios = defaultdict(lambda: defaultdict(dict))
        for rec, review in zip(records, sem):
            if rec["repetition"] == 1:
                scenarios[rec["scenario_id"]][rec["arm"]][rec["variant"]] = review["semantic_success"]
        scenario_results = {}
        for sid, arms in scenarios.items():
            if all(set(arms.get(arm, {})) == {"formal", "paraphrase"}
                   and None not in arms[arm].values() for arm in ("baseline", "candidate")):
                scenario_results[sid] = {
                    arm: all(arms[arm].values()) for arm in ("baseline", "candidate")
                }
        summary["semantic_review"] = {
            "sha256": sha(semantic_path), "reviewed_records": len(sem),
            "scored_outputs": sum(r["semantic_success"] is not None for r in sem),
            "successful_outputs": sum(r["semantic_success"] is True for r in sem),
            "complete_paired_expressions": len(complete), "pair_counts": pair_counts,
            "complete_scenarios": scenario_results,
            "new_unsupported_claims": [r["index"] for r in sem
                                       if r["grounded"] is False],
            "new_wrong_deadline_indices": [r["index"] for r in sem
                                           if r["unsafe_deadline"] is True],
        }
    (OUT / "automatic_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    main(parser.parse_args().output_dir)
