"""Offline audits and paired summaries for the completed deadline challenge."""
from __future__ import annotations

import hashlib
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema

OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []


def write_lines(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def date_found(text, day):
    y, m, d = map(int, day.split("-"))
    patterns = [rf"{y}年\s*0?{m}月\s*0?{d}日", rf"{y}[-/]0?{m}[-/]0?{d}(?!\d)"]
    return any(re.search(p, text) for p in patterns)


def time_found(text, moment):
    h, m = map(int, moment.split(":"))
    return bool(re.search(rf"(?<!\d)0?{h}:0?{m}(?!\d)", text) or
                re.search(rf"(?<!\d)0?{h}時(?:0?{m}分)?(?!\d)", text) and (m == 0 or re.search(rf"0?{h}時\s*0?{m}分", text)))


def bootstrap_interval(scenario_delta, seed=20261009, nboot=20000):
    rng = random.Random(seed)
    values = list(scenario_delta)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(nboot))
    return [means[int(nboot * .025)], means[int(nboot * .975)]]


def main():
    manifest = read(OUT / "manifest.json")
    assert all(sha(OUT / k) == manifest[v] for k, v in (("challenge.json", "fixture_sha256"),
        ("frozen_tasks.json", "tasks_sha256"), ("frozen_schema.json", "schema_sha256")))
    tasks = read(OUT / "frozen_tasks.json")
    fixture = {r["id"]: r for r in read(OUT / "challenge.json")}
    schema = read(OUT / "frozen_schema.json")
    attempts = lines(OUT / "api_attempts.jsonl")
    assert len(attempts) <= manifest["max_total_api_attempts"]
    for i, a in enumerate(attempts):
        t = tasks[a["task_index"]]
        assert i == a["attempt_index"]
        assert all(a[k] == t[k] for k in ("id", "scenario_id", "variant", "arm", "repetition", "prompt_sha256"))
    selected = {}
    for a in attempts:
        if a.get("valid_output") and a["task_index"] not in selected:
            selected[a["task_index"]] = a
    records = []
    auto = []
    blind = []
    for i, t in enumerate(tasks):
        a = selected.get(i)
        if a is None:
            continue
        row = fixture[t["id"]]
        data = a["data"]
        jsonschema.validate(data, schema)
        assert json.loads(a["raw_text"]) == data
        valid_ids = {e["element_id"] for e in row["evidence"]}
        citation_ok = bool(data["claims"]) and all(bool(c["evidence_element_ids"]) and
            set(c["evidence_element_ids"]) <= valid_ids for c in data["claims"])
        text = "\n".join(c["text"] for c in data["claims"])
        gold = row["gold"]
        check = {
            "task_index": i, "attempt_index": a["attempt_index"], "id": t["id"], "scenario_id": t["scenario_id"],
            "variant": t["variant"], "arm": t["arm"], "repetition": t["repetition"],
            "schema_ok": True, "citation_ids_ok": citation_ok,
            "date_proxy": {v: date_found(text, v) for v in gold["required_dates"]},
            "time_proxy": {v: time_found(text, v) for v in gold["required_times"]},
            "proxy_not_semantic_score": True,
        }
        auto.append(check)
        records.append(dict(a, index=i))
        blind_id = hashlib.sha256(f"deadline-blind-20261009-{i}".encode()).hexdigest()[:12]
        blind.append({"blind_id": blind_id, "scenario_id": t["scenario_id"], "variant": t["variant"],
            "repetition": t["repetition"], "question": row["question"], "evidence": row["evidence"],
            "gold": gold, "review_note": row["review_note"], "raw_text": a["raw_text"],
            "claims": data["claims"], "missing_conditions": data["missing_conditions"], "citation_ids_ok": citation_ok})
    rng = random.Random(20261009)
    rng.shuffle(blind)
    write_lines(OUT / "api_records.jsonl", records)
    write_lines(OUT / "automatic_checks.jsonl", auto)
    write_lines(OUT / "blind_review_sheet.jsonl", blind)
    write_lines(OUT / "blind_mapping.jsonl", [{"blind_id": hashlib.sha256(f"deadline-blind-20261009-{i}".encode()).hexdigest()[:12],
        "task_index": i, "arm": tasks[i]["arm"]} for i in range(len(tasks))])
    summary = {"planned_tasks": len(tasks), "valid_tasks": len(selected), "api_attempts": len(attempts),
        "failed_attempts": sum(not a.get("valid_output") for a in attempts),
        "error_types": dict(Counter(a.get("error_type") for a in attempts if not a.get("valid_output"))),
        "schema_invalid_selected": 0, "citation_invalid_selected": sum(not x["citation_ids_ok"] for x in auto),
        "input_tokens": sum((a.get("usage") or {}).get("prompt_token_count") or 0 for a in attempts),
        "output_and_thought_tokens": sum(((a.get("usage") or {}).get("candidates_token_count") or 0) +
            ((a.get("usage") or {}).get("thoughts_token_count") or 0) for a in attempts),
        "estimated_usd": sum(a.get("estimated_usd", 0) for a in attempts),
        "latency_p50_s_all_attempts": statistics.median(a["latency_s"] for a in attempts) if attempts else None,
        "latency_p95_s_all_attempts": sorted(a["latency_s"] for a in attempts)[int((len(attempts)-1)*.95)] if attempts else None,
        "attempts_sha256": sha(OUT / "api_attempts.jsonl"), "records_sha256": sha(OUT / "api_records.jsonl"),
        "scope": "automatic integrity and string proxies; semantic judgments separate"}
    (OUT / "automatic_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    reviews = lines(OUT / "semantic_review.jsonl")
    if not reviews:
        print(json.dumps(summary, ensure_ascii=False, indent=2)); return
    assert len(reviews) == len(tasks)
    by_idx = {r["task_index"]: r for r in reviews}
    assert set(by_idx) == set(range(len(tasks)))
    by_pair = defaultdict(dict)
    for i, t in enumerate(tasks):
        r = by_idx[i]
        assert r["semantic_success"] is not None
        by_pair[(t["id"], t["repetition"])][t["arm"]] = r["semantic_success"]
    assert len(by_pair) == 60 and all(len(p) == 2 for p in by_pair.values())
    pair_counts = {"both_pass": 0, "baseline_only": 0, "candidate_only": 0, "both_fail": 0}
    for p in by_pair.values():
        key = ("both_pass" if p["baseline"] and p["candidate"] else "baseline_only" if p["baseline"]
               else "candidate_only" if p["candidate"] else "both_fail")
        pair_counts[key] += 1
    scenarios = {}
    for sid in sorted({t["scenario_id"] for t in tasks}):
        selected_idx = [i for i,t in enumerate(tasks) if t["scenario_id"] == sid and t["repetition"] == 1]
        assert len(selected_idx) == 4
        arms = {arm: all(by_idx[i]["semantic_success"] for i in selected_idx if tasks[i]["arm"] == arm)
                for arm in ("baseline", "candidate")}
        scenarios[sid] = arms
    scenario_counts = {"both_pass": 0, "baseline_only": 0, "candidate_only": 0, "both_fail": 0}
    for p in scenarios.values():
        key = ("both_pass" if p["baseline"] and p["candidate"] else "baseline_only" if p["baseline"]
               else "candidate_only" if p["candidate"] else "both_fail")
        scenario_counts[key] += 1
    deltas = [int(v["candidate"]) - int(v["baseline"]) for v in scenarios.values()]
    systems = defaultdict(list)
    for sid, result in scenarios.items():
        row = fixture[f"{sid}-formal"]
        systems[row["system_name"]].append((sid, result))
    repeats = {}
    for arm in ("baseline", "candidate"):
        v = [(t["id"], by_idx[i]["semantic_success"]) for i,t in enumerate(tasks) if t["arm"] == arm and t["scenario_id"] in manifest["repetition_subset"]]
        first = {x:y for x,y in v[:12]}
        second = {x:y for x,y in v[12:]}
        assert first.keys() == second.keys()
        repeats[arm] = {"consistent": sum(first[x] == second[x] for x in first), "total": len(first),
                        "discordant_ids": [x for x in first if first[x] != second[x]]}
    summary["semantic"] = {
        "review_sha256": sha(OUT / "semantic_review.jsonl"), "successful_outputs": sum(r["semantic_success"] for r in reviews),
        "paired_expression_outcomes_including_repeats": pair_counts,
        "scenario_outcomes_primary_repetition_1": scenario_counts,
        "scenario_net_improvements": sum(deltas), "scenario_mean_paired_difference": sum(deltas)/len(deltas),
        "scenario_clustered_bootstrap_95pct_ci": bootstrap_interval(deltas),
        "scenarios": scenarios,
        "system_slices": {name: {"n_scenarios": len(items), "baseline_pass": sum(v["baseline"] for _,v in items),
            "candidate_pass": sum(v["candidate"] for _,v in items), "ids": [sid for sid,_ in items]}
            for name, items in systems.items()},
        "repetition_consistency": repeats,
        "new_unsafe_deadline_task_indices": [i for i,t in enumerate(tasks) if t["arm"] == "candidate" and
            by_idx[i]["unsafe_deadline"] and not by_idx[i-1]["unsafe_deadline"]],
        "new_unsupported_claim_task_indices": [i for i,t in enumerate(tasks) if t["arm"] == "candidate" and
            not by_idx[i]["grounded"] and by_idx[i-1]["grounded"]],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary["semantic"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
