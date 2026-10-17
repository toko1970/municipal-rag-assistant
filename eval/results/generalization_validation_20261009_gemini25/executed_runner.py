"""Frozen, bounded paired development challenge for one deadline prompt candidate.

Prepare before API use, then run once. Analyze saved responses without API calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval/results/generalization_validation_20261009_gemini25"
CHALLENGE = OUT / "challenge.json"
MODEL = "gemini-2.5-flash"
BASE = (
    "次の質問へ、取得根拠だけを使って回答してください。自由文の最終回答や分類は返さず、"
    "answer-output-v1のJSONだけを返してください。すべてのclaimにelement_idを引用してください。\n"
    "画像が添付される場合、visual_asset.attachment_indexが添付順（1始まり）です。\n"
)
EXTRA = "期限を回答するときは、具体的な年月日と時刻まで答えてください。\n"
REPEAT_SCENARIOS = ("D01", "D04", "D12", "D13", "D17", "D20")
PRICE = {"input_usd_per_million": 0.30, "output_usd_per_million": 2.50}
MAX_CALLS = 120
MAX_ESTIMATED_USD = 0.50


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prompt(row: dict, arm: str) -> str:
    # Strict allowlist: gold, review_note, family, and all scorer data stay out.
    evidence = [
        {k: item[k] for k in ("element_id", "content", "document_name", "heading")}
        for item in row["evidence"]
    ]
    return (EXTRA if arm == "candidate" else "") + BASE + (
        f"質問: {row['question']}\n取得根拠: "
        + json.dumps(evidence, ensure_ascii=False)
    )


def prepare() -> None:
    import jsonschema

    assert sha(CHALLENGE) == "67fdfc876ccfb1489a570b8437b524fbee484cf02bbcee2cd40cf687ab5896dd"
    rows = json.loads(CHALLENGE.read_text())
    assert len(rows) == 48 and len({r["scenario_id"] for r in rows}) == 24
    schema_path = ROOT / "design/schemas/answer-output-v1.schema.json"
    schema = json.loads(schema_path.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    tasks = []
    for r in rows:
        for arm in ("baseline", "candidate"):
            p = prompt(r, arm)
            tasks.append({"id": r["id"], "scenario_id": r["scenario_id"],
                          "variant": r["variant"], "arm": arm, "repetition": 1,
                          "prompt": p, "prompt_sha256": hashlib.sha256(p.encode()).hexdigest()})
    for r in rows:
        if r["scenario_id"] in REPEAT_SCENARIOS:
            for arm in ("baseline", "candidate"):
                p = prompt(r, arm)
                tasks.append({"id": r["id"], "scenario_id": r["scenario_id"],
                              "variant": r["variant"], "arm": arm, "repetition": 2,
                              "prompt": p, "prompt_sha256": hashlib.sha256(p.encode()).hexdigest()})
    assert len(tasks) == MAX_CALLS
    if any((OUT / name).exists() for name in ("frozen_tasks.json", "api_records.jsonl", "manifest.json")):
        raise RuntimeError("Experiment already prepared; refusing to overwrite")
    write_json(OUT / "frozen_tasks.json", tasks)
    write_json(OUT / "frozen_schema.json", schema)
    shutil.copyfile(__file__, OUT / "executed_runner.py")
    write_json(OUT / "manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "precommitted_before_api", "fixture_sha256": sha(CHALLENGE),
        "tasks_sha256": sha(OUT / "frozen_tasks.json"),
        "schema_sha256": sha(OUT / "frozen_schema.json"),
        "runner_sha256": sha(OUT / "executed_runner.py"),
        "model": MODEL, "temperature": 0, "seed": 42,
        "thinking_budget": 0,
        "max_output_tokens": 1024, "http_timeout_ms": 45000, "http_attempts": 1,
        "max_calls": MAX_CALLS, "max_estimated_usd": MAX_ESTIMATED_USD,
        "price_assumption": PRICE,
        "price_source": "https://ai.google.dev/gemini-api/docs/pricing (Gemini 2.5 Flash Standard, 2026-10-09); estimated, not actual billing",
        "switch_reason": "Gemini 3.1 Flash-Lite returned quota 429 after 15 valid responses. This is a separate full paired run with a different model; outputs are never mixed. Model change limits comparison with the previous exploration and production configuration.",
        "candidate": EXTRA.strip(), "changed_layer": "generation prompt only",
        "primary_metric": "24 scenario-level paired composite outcomes; each scenario succeeds only if both expressions pass semantic content review",
        "adoption_gate_for_next_stage": "candidate net improvement >=3 scenarios, zero new answerable-scenario regressions, zero new unsafe concrete deadlines on five must-abstain scenarios; all expressions must have valid grounded output",
        "repetition_subset": REPEAT_SCENARIOS,
        "repetition_rule": "2 runs per arm for both expressions of these six scenarios; all other tasks once; no best-response selection",
        "comparison": "Same fixed evidence, schema, model, temperature, seed, and output cap. Alternate arms for each expression. No retrieval or classifier/display path.",
        "scope": "Development challenge, not sealed holdout or representative accuracy. Existing 130/100 regression and fresh sealed holdout only if gate passes.",
        "review_round_limit": 2,
    })


def run() -> None:
    import config
    from google import genai
    from google.genai import types as gt
    from src.llm_provider import _gemini_compatible_schema

    if (OUT / "api_records.jsonl").exists():
        raise RuntimeError("API record exists; refusing duplicate run")
    tasks_path = OUT / "frozen_tasks.json"
    manifest = json.loads((OUT / "manifest.json").read_text())
    assert sha(tasks_path) == manifest["tasks_sha256"]
    assert sha(OUT / "frozen_schema.json") == manifest["schema_sha256"]
    assert sha(CHALLENGE) == manifest["fixture_sha256"]
    tasks = json.loads(tasks_path.read_text())
    schema = json.loads((OUT / "frozen_schema.json").read_text())
    assert len(tasks) <= MAX_CALLS
    if not config.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY unavailable")
    client = genai.Client(
        api_key=config.GOOGLE_API_KEY,
        http_options=gt.HttpOptions(timeout=45000, retry_options=gt.HttpRetryOptions(attempts=1)),
    )
    spent = 0.0
    with (OUT / "api_records.jsonl").open("x") as file:
        for i, task in enumerate(tasks):
            reserve = ((len(task["prompt"].encode()) + 3000) * PRICE["input_usd_per_million"]
                       + 1024 * PRICE["output_usd_per_million"]) / 1_000_000
            if spent + reserve > MAX_ESTIMATED_USD:
                raise RuntimeError(f"Estimated cost cap before task {i}")
            rec = {k: v for k, v in task.items() if k != "prompt"}
            rec["index"] = i
            start = time.perf_counter()
            try:
                response = client.models.generate_content(
                    model=MODEL, contents=task["prompt"],
                    config=gt.GenerateContentConfig(
                        temperature=0, seed=42, max_output_tokens=1024,
                        thinking_config=gt.ThinkingConfig(thinking_budget=0),
                        response_mime_type="application/json",
                        response_json_schema=_gemini_compatible_schema(schema),
                    ),
                )
                rec["raw_text"] = response.text
                rec["data"] = json.loads(response.text)
                rec["usage"] = response.usage_metadata.model_dump() if response.usage_metadata else {}
                rec["model_version"] = response.model_version
                inp = rec["usage"].get("prompt_token_count") or 0
                out = (rec["usage"].get("candidates_token_count") or 0) + (rec["usage"].get("thoughts_token_count") or 0)
                rec["estimated_usd"] = (inp * PRICE["input_usd_per_million"] + out * PRICE["output_usd_per_million"]) / 1_000_000
                spent += rec["estimated_usd"]
            except Exception as exc:
                rec["error_type"] = type(exc).__name__
                rec["error"] = str(exc)[:1000]
                rec["estimated_usd"] = 0
            rec["latency_s"] = round(time.perf_counter() - start, 3)
            rec["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            file.write(json.dumps(rec, ensure_ascii=False) + "\n")
            file.flush()
            if (i + 1) % 12 == 0:
                print(f"completed {i+1}/{len(tasks)} calls; estimated USD {spent:.5f}", flush=True)
            if "error" in rec and ("quota" in rec["error"].lower() or "RESOURCE_EXHAUSTED" in rec["error"]):
                print("Quota error: stopping after this recorded attempt", flush=True)
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "run"])
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    if args.mode == "prepare":
        prepare()
    else:
        run()
