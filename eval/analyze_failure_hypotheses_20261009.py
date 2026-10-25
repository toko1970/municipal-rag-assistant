"""Offline analysis of bounded experiment; never makes API calls."""

import hashlib
import json
import re
from pathlib import Path

P = (
    Path(__file__).resolve().parents[1]
    / "eval/results/failure_hypotheses_verification_20261009"
)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(n):
    return json.loads((P / n).read_text())


def write(n, x):
    (P / n).write_text(json.dumps(x, ensure_ascii=False, indent=2) + "\n")


records = [json.loads(line) for line in (P / "api_records.jsonl").read_text().splitlines()]
tasks = read("tasks.json")
manifest = read("manifest.json")
assert sha(P / "tasks.json") == manifest["tasks_sha256"]
assert sha(P / "schemas.json") == manifest["schemas_sha256"]
for r in records:
    t = tasks[r["task_index"]]
    assert hashlib.sha256(t["prompt"].encode()).hexdigest() == r["prompt_sha256"]
    assert r["id"] == t["id"] and r["arm"] == t["arm"]
    if r["family"] == "classification" and r["origin"].startswith("historical"):
        assert t["answer"]["missing_conditions"] == []
classified = [r for r in records if r["family"] == "classification" and not r["error"]]
summary = {
    "input_hashes_verified": True,
    "completed": len(records),
    "planned": len(tasks),
    "groups": {},
    "paired": [],
    "deadline_control": [],
}
for origin in sorted({r["origin"] for r in classified}):
    rr = [r for r in classified if r["origin"] == origin]
    summary["groups"][origin] = {
        arm: {
            "n": sum(r["arm"] == arm for r in rr),
            "correct": sum(r["arm"] == arm and r["correct"] for r in rr),
        }
        for arm in ["baseline", "scope_definition"]
    }
    for id in sorted({r["id"] for r in rr}):
        pair = [r for r in rr if r["id"] == id]
        summary["paired"].append(
            {
                "id": id,
                "origin": origin,
                "expected_label": pair[0]["expected_label"],
                "labels": {r["arm"]: r["label"] for r in pair},
                "factors": {r["arm"]: r["data"]["factors"] for r in pair},
            }
        )
semantic = []
for r in records:
    if r["family"] == "deadline" and not r["error"]:
        override = (r["id"], r["arm"]) in [
            ("TH011/paraphrase_or_noisy", "calculation_permission"),
            ("TH039/paraphrase_or_noisy", "deadline_only"),
        ]
        semantic.append(
            {
                "id": r["id"],
                "arm": r["arm"],
                "strict_regex_correct": r["correct"],
                "semantic_date_time_correct": True if override else r["correct"],
                "note": "同一claimに2027年の実施日と、省略年の締切月日・時刻を記載。年参照が一意なので具体期限として合格。厳密年月日連続regexのみが不合格。"
                if override
                else "生claim内容を確認し自動判定と意味判定が一致。",
            }
        )
write("deadline_semantic_review.json", semantic)
for arm in ["baseline", "explicit_date", "calculation_permission", "deadline_only"]:
    rr = [
        r
        for r in records
        if r["family"] == "deadline" and r["arm"] == arm and not r["error"]
    ]
    summary["groups"]["deadline/" + arm] = {
        "n": len(rr),
        "correct_date_and_time": sum(r["correct"] for r in rr),
        "ids_correct": [r["id"] for r in rr if r["correct"]],
        "semantic_correct": sum(
            x["semantic_date_time_correct"] for x in semantic if x["arm"] == arm
        ),
    }
for r in records:
    if r["family"] == "deadline_control" and not r["error"]:
        text = "\n".join(c["text"] for c in r["data"]["claims"])
        correct = bool(
            re.search(r"2027\s*(?:年|/|-)\s*0?5\s*(?:月|/|-)\s*17(?:日)?", text)
        ) and bool(re.search(r"23時|23:00|午後11時", text))
        summary["deadline_control"].append(
            {
                "id": r["id"],
                "expected_date": "2027-05-17",
                "expected_time": "23:00",
                "date_and_time_ok": correct,
                "text": text,
            }
        )
summary["cost"] = {
    "valid_run_estimated_usd": sum(r.get("estimated_cost_usd", 0) for r in records),
    "invalidated_run_estimated_usd": read("invalidated_round0/invalidation.json")[
        "estimated_cost_usd"
    ],
}
summary["cost"]["campaign_estimated_usd"] = sum(summary["cost"].values())
summary["campaign_calls"] = (
    len(records) + read("invalidated_round0/invalidation.json")["completed_calls"]
)
if (P / "api_summary.json").exists():
    raw = read("api_summary.json")
    for k, v in raw["groups"].items():
        if k.startswith("deadline_control/"):
            v["correct"] = None
            v["scoring_note"] = (
                "Runner did not score this control; see reviewed_analysis.deadline_control for offline date/time scoring."
            )
    write("api_summary.json", raw)
write("reviewed_analysis.json", summary)
# Verify the additional two-axis run and recompute whole-campaign accounting offline.
if (P / "two_axes_round2/records.jsonl").exists():
    m2 = read("two_axes_round2/manifest.json")
    t2 = read("two_axes_round2/tasks.json")
    assert sha(P / "two_axes_round2/tasks.json") == m2["tasks_sha256"]
    assert sha(P / "two_axes_round2/schema.json") == m2["schema_sha256"]
    extra = [
        json.loads(x)
        for x in (P / "two_axes_round2/records.jsonl").read_text().splitlines()
    ]
    for r, t in zip(extra, t2):
        assert (
            r["id"] == t["id"]
            and r["prompt_sha256"] == hashlib.sha256(t["prompt"].encode()).hexdigest()
        )
        assert r["expected"] == t["expected"]
    assert len(extra) == len(t2) == 4
    invalid = [
        json.loads(x)
        for x in (P / "invalidated_round0/api_records.jsonl").read_text().splitlines()
    ]
    all_records = records + extra + invalid
    campaign = {
        "total_calls": len(all_records),
        "valid_calls": len(records) + len(extra),
        "invalidated_calls": len(invalid),
        "errors": sum(r.get("error") is not None for r in all_records),
        "input_tokens": sum(
            r.get("usage", {}).get("prompt_token_count") or 0 for r in all_records
        ),
        "output_tokens": sum(
            r.get("usage", {}).get("candidates_token_count") or 0 for r in all_records
        ),
        "thought_tokens": sum(
            r.get("usage", {}).get("thoughts_token_count") or 0 for r in all_records
        ),
        "estimated_cost_usd": sum(r.get("estimated_cost_usd", 0) for r in all_records),
        "max_estimated_cost_usd": 0.1,
        "review_revalidation_count": 2,
        "additional_api_execution_required": False,
    }
    write("campaign_summary.json", campaign)
    for fname, snapshot, key in [
        ("manifest.json", "executed_runner_round1.py", "source_sha256"),
        (
            "two_axes_round2/manifest.json",
            "two_axes_round2/executed_runner.py",
            "script_sha256",
        ),
    ]:
        assert read(fname)[key] == sha(P / snapshot)
print(json.dumps(summary, ensure_ascii=False, indent=2))
