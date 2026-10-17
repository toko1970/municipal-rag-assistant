"""Resume-safe, precommitted full deadline challenge. No quality-based replacement."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT))
MODEL = "gemini-3.1-flash-lite"
PRICE = (0.25, 1.50)  # USD per 1M tokens; estimate, not actual billing
MAX_ATTEMPTS = 160
MAX_COST = 1.0
MAX_WALL_S = 2400
MIN_START_INTERVAL_S = 6.2
MAX_RETRIES_PER_TASK = 2


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def load_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def retry_seconds(message):
    matches = re.findall(r"(?:retryDelay|retry_delay|retry in|retry_after|Retry-After)[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*s?", message, re.I)
    if not matches:
        matches = re.findall(r"(?:seconds:|seconds=|retry_delay\s*\{\s*seconds:)\s*([0-9]+)", message, re.I)
    return max(map(float, matches), default=0.0)


def prepare():
    source = ROOT / "eval/results/generalization_validation_20261009"
    if (OUT / "manifest.json").exists():
        raise RuntimeError("Already prepared; refusing to overwrite")
    for name in ("challenge.json", "frozen_tasks.json", "frozen_schema.json"):
        (OUT / name).write_bytes((source / name).read_bytes())
    tasks = json.loads((OUT / "frozen_tasks.json").read_text())
    fixture = json.loads((OUT / "challenge.json").read_text())
    assert len(tasks) == 120 and len(fixture) == 48
    assert len({r["scenario_id"] for r in fixture}) == 24
    assert [t["repetition"] for t in tasks].count(2) == 24
    assert sha(OUT / "challenge.json") == "67fdfc876ccfb1489a570b8437b524fbee484cf02bbcee2cd40cf687ab5896dd"
    for t in tasks:
        assert hashlib.sha256(t["prompt"].encode()).hexdigest() == t["prompt_sha256"]
        assert "gold" not in t["prompt"] and "review_note" not in t["prompt"]
    dump(OUT / "manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "precommitted_before_api", "source_experiment": str(source.relative_to(ROOT)),
        "fixture_sha256": sha(OUT / "challenge.json"), "tasks_sha256": sha(OUT / "frozen_tasks.json"),
        "schema_sha256": sha(OUT / "frozen_schema.json"), "runner_sha256": sha(OUT / "runner.py"),
        "model": MODEL, "temperature": 0, "seed": 42, "max_output_tokens": 1024,
        "http_timeout_ms": 45000, "sdk_http_attempts": 1,
        "planned_valid_tasks": 120, "max_total_api_attempts": MAX_ATTEMPTS,
        "max_retries_per_task": MAX_RETRIES_PER_TASK, "min_start_interval_s": MIN_START_INTERVAL_S,
        "retry_on": ["429", "503", "timeout", "transport", "invalid_json_or_schema"],
        "retry_rule": "RetryInfo delay plus 2 seconds, also subject to 6.2-second minimum start interval. At most two retries for a task. Preserve all attempts. Never replace a schema-valid answer based on content quality.",
        "http_503_rule": "Transient provider failure; record original error and retry at most twice, then mark task incomplete.",
        "max_estimated_usd": MAX_COST, "max_wall_seconds": MAX_WALL_S,
        "cost_assumption_usd_per_million_input_output": PRICE,
        "cost_note": "Estimate from returned usage. Failed calls without usage may be billed and cannot be included exactly.",
        "candidate": "期限を回答するときは、具体的な年月日と時刻まで答えてください。",
        "adoption_gate": "Net >=3 scenario improvements, zero new answerable-scenario regressions, zero new unsafe deadlines on five must-abstain scenarios, all valid grounded outputs; default reject from previous observations.",
        "repetition_subset": ["D01", "D04", "D12", "D13", "D17", "D20"],
        "quality_early_stop": False,
        "scope": "Fixed-evidence generation-only development challenge; opened set, not independent holdout; existing records remain immutable.",
        "review_round_limit": 2,
    })


def run():
    import config
    import jsonschema
    from google import genai
    from google.genai import types as gt
    from src.llm_provider import _gemini_compatible_schema

    manifest = json.loads((OUT / "manifest.json").read_text())
    assert all(sha(OUT / k) == manifest[v] for k, v in (("challenge.json", "fixture_sha256"), ("frozen_tasks.json", "tasks_sha256"), ("frozen_schema.json", "schema_sha256")))
    continuation = json.loads((OUT / "continuation_manifest.json").read_text())
    assert sha(OUT / "runner.py") == manifest["runner_sha256"]
    assert sha(OUT / "runner_continuation.py") == continuation["runner_sha256"]
    tasks = json.loads((OUT / "frozen_tasks.json").read_text())
    schema = json.loads((OUT / "frozen_schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    if not config.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY unavailable")
    client = genai.Client(api_key=config.GOOGLE_API_KEY, http_options=gt.HttpOptions(timeout=45000, retry_options=gt.HttpRetryOptions(attempts=1)))
    path = OUT / "api_attempts.jsonl"
    old = load_lines(path)
    done = {r["task_index"] for r in old if r.get("valid_output") is True or
            (r.get("valid_output") is False and not r.get("retryable"))}
    attempts_by_task = {i: sum(r["task_index"] == i for r in old) for i in range(len(tasks))}
    spent = sum(r.get("estimated_usd", 0) for r in old)
    if old and any(old[i]["attempt_index"] != i for i in range(len(old))):
        raise RuntimeError("Nonconsecutive attempts ledger")
    start = time.monotonic()
    elapsed_before_resume = (datetime.now(timezone.utc) - datetime.fromisoformat(manifest["created_at_utc"])).total_seconds()
    last_start = None
    with path.open("a") as file:
        for task_index, task in enumerate(tasks):
            if task_index in done:
                continue
            while attempts_by_task[task_index] < 1 + MAX_RETRIES_PER_TASK:
                if len(old) >= MAX_ATTEMPTS or elapsed_before_resume + time.monotonic() - start >= MAX_WALL_S:
                    print("LIMIT: attempts or wall time", flush=True)
                    return
                # Conservative reserve per request, including worst-case 1024 output tokens.
                reserve = ((len(task["prompt"].encode()) + 3000) * PRICE[0] + 1024 * PRICE[1]) / 1_000_000
                if spent + reserve > MAX_COST:
                    print("LIMIT: estimated cost", flush=True)
                    return
                delay = max(0, MIN_START_INTERVAL_S - (time.monotonic() - last_start)) if last_start else 0
                if old and old[-1].get("task_index") == task_index and old[-1].get("retryable"):
                    delay = max(delay, old[-1].get("retry_info_seconds", 0) + 2)
                if delay:
                    time.sleep(delay)
                last_start = time.monotonic()
                rec = {k: task[k] for k in ("id", "scenario_id", "variant", "arm", "repetition", "prompt_sha256")}
                rec.update(task_index=task_index, attempt_index=len(old), attempt_number=attempts_by_task[task_index] + 1,
                           started_at_utc=datetime.now(timezone.utc).isoformat())
                try:
                    response = client.models.generate_content(model=MODEL, contents=task["prompt"], config=gt.GenerateContentConfig(
                        temperature=0, seed=42, max_output_tokens=1024, response_mime_type="application/json",
                        response_json_schema=_gemini_compatible_schema(schema)))
                    rec["raw_text"] = response.text
                    rec["usage"] = response.usage_metadata.model_dump() if response.usage_metadata else {}
                    rec["model_version"] = response.model_version
                    u = rec["usage"]
                    inp = u.get("prompt_token_count") or 0
                    output = (u.get("candidates_token_count") or 0) + (u.get("thoughts_token_count") or 0)
                    rec["estimated_usd"] = (inp * PRICE[0] + output * PRICE[1]) / 1_000_000
                    data = json.loads(response.text)
                    jsonschema.validate(data, schema)
                    rec["data"] = data
                    rec["valid_output"] = True
                    rec["retryable"] = False
                except Exception as exc:
                    rec["valid_output"] = False
                    rec["error_type"] = type(exc).__name__
                    rec["error"] = str(exc)[:2000]
                    rec.setdefault("estimated_usd", 0.0)
                    msg = rec["error"].lower()
                    rec["retryable"] = any(s in msg for s in ("429", "resource_exhausted", "503", "unavailable", "timeout", "timed out", "connection", "transport"))
                    rec["retry_info_seconds"] = retry_seconds(rec["error"])
                rec["latency_s"] = round(time.monotonic() - last_start, 3)
                rec["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
                file.write(json.dumps(rec, ensure_ascii=False) + "\n")
                file.flush()
                old.append(rec)
                attempts_by_task[task_index] += 1
                spent += rec["estimated_usd"]
                if rec["valid_output"]:
                    done.add(task_index)
                    break
                if not rec["retryable"]:
                    break
            if (task_index + 1) % 12 == 0:
                print(f"task {task_index+1}/120; valid {len(done)}; attempts {len(old)}; estimated USD {spent:.5f}", flush=True)
    print(f"COMPLETE: valid {len(done)}/120; attempts {len(old)}; estimated USD {spent:.5f}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "run"):
        raise SystemExit("usage: runner.py prepare|run")
    globals()[sys.argv[1]]()
