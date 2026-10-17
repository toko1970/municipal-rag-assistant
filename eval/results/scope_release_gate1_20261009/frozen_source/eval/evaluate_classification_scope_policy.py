"""Freeze/run a bounded paired classifier-only development experiment.

Prepare: python -m eval.evaluate_classification_scope_policy --output-dir PATH
Run frozen tasks: same command with --run (refuses an already started run).
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import time
from uuid import NAMESPACE_URL, UUID, uuid5

import jsonschema

from config import BASE_DIR, CLASSIFIER_MODEL_NAME
from src.answering import derive_label, parse_answer_output, parse_classification_output, render_display_answer, validate_answer_evidence
from src.classification_scope_policy import PROMPT_VERSION, SCOPE_POLICY, build_scope_classification_prompt_from_payload
from src.query_service import build_classification_prompt_v1_from_payload

SOURCE = BASE_DIR / "eval/results/generalization_completion_20261009/classification"
SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
REPEAT_IDS = {"A02-paraphrase", "A03-formal", "A04-formal", "C01-formal"}
SOURCE_FILES = ["src/classification_scope_policy.py", "src/query_service.py", "src/answering.py",
                "eval/evaluate_classification_scope_policy.py", "design/schemas/classification-output-v1.schema.json"]


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def readl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def build_cases():
    gold = {r["id"]: r for r in json.loads((SOURCE / "challenge.json").read_text())}
    attempts = readl(SOURCE / "api_attempts.jsonl")
    cases = []
    for a in attempts:
        task = a["task"]
        if (a["phase"] != "v1_classification" or task["evidence_mode"] != "oracle"
                or task["repetition"] != 1 or task["scenario_id"] in {"A01", "B01"}):
            continue
        payload = json.loads(a["prompt"].split("判定対象: ", 1)[1])
        assert set(payload) == {"question", "retrieved_evidence", "generated_answer"}
        cases.append({"id": task["row_id"], "scenario_id": task["scenario_id"], "kind": "known_development",
                      "payload": payload, "expected_label": gold[task["row_id"]]["gold"]["label"],
                      "expected_factors": {}, "source_prompt_sha256": a["prompt_sha256"]})
    assert len(cases) == 20
    # Diagnostic controls are not independent unseen generalization evidence.
    controls = [
        ("D01", "架空の特別作業手当について、勤務記録と対象作業の要件は満たしています。私への支給を確定できますか。",
         "対象作業と勤務記録の要件を満たしても、支給は審査委員会が業務上の必要性を審査して裁量で決定する。",
         ["要件を満たしても審査委員会の裁量による決定が残るため、支給は確定できません。"],
         "判断要", {"retrieval_sufficient": True, "answer_fully_supported": True, "requires_case_facts": False, "requires_policy_judgment": True, "version_conflict": False}),
        ("D02", "架空の設備点検補助について、2027年4月1日の適用単価はいくらですか。",
         "同じ対象と施行日2027年4月1日を持つ通知甲は単価200円、通知乙は単価300円と規定する。両通知とも有効と記載され、優先関係の記載はない。",
         ["同じ適用日に200円と300円の記載が競合し、優先関係がないため適用単価を一意に決められません。"],
         "判断要", {"retrieval_sufficient": True, "answer_fully_supported": True, "requires_case_facts": False, "requires_policy_judgment": False, "version_conflict": True}),
        ("D03", "架空の研修資料費は1冊につきいくらですか。",
         "研修資料費は1冊につき500円とする。",
         ["研修資料費は1冊につき900円です。"],
         None, {"retrieval_sufficient": True, "answer_fully_supported": False, "requires_case_facts": False, "requires_policy_judgment": False, "version_conflict": False}),
        ("D04", "架空の研修資料費の単価と提出先を教えてください。",
         "研修資料費は1冊につき500円とする。申請の提出先は研修室とする。",
         ["研修資料費は1冊につき500円です。"],
         None, {"retrieval_sufficient": True, "answer_fully_supported": False, "requires_case_facts": False, "requires_policy_judgment": False, "version_conflict": False}),
    ]
    for cid, question, content, claims, label, factors in controls:
        eid = str(uuid5(NAMESPACE_URL, "scope-policy-" + cid))
        cases.append({"id": cid, "scenario_id": cid, "kind": "diagnostic_control",
                      "expected_label": label, "expected_factors": factors,
                      "payload": {"question": question,
                                  "retrieved_evidence": [{"element_id": eid, "content": content}],
                                  "generated_answer": {"schema_version": "1.0", "claims": [
                                      {"claim_id": f"claim-{i}", "ordinal": i, "text": text,
                                       "evidence_element_ids": [eid], "evidence_kind": "text"}
                                      for i, text in enumerate(claims, 1)], "missing_conditions": []}}})
    return cases


def make_tasks(cases):
    rng = random.Random(20261009)
    ordered = list(cases)
    rng.shuffle(ordered)
    tasks = []
    for repetition in (1, 2):
        for i, case in enumerate(ordered):
            if repetition == 2 and case["id"] not in REPEAT_IDS:
                continue
            arms = ("baseline", "candidate") if (i + repetition) % 2 else ("candidate", "baseline")
            p = case["payload"]
            for arm in arms:
                builder = build_classification_prompt_v1_from_payload if arm == "baseline" else build_scope_classification_prompt_from_payload
                prompt = builder(p["question"], p["retrieved_evidence"], p["generated_answer"])
                tasks.append({"case_id": case["id"], "arm": arm, "repetition": repetition,
                              "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()})
    return tasks


def prepare(out):
    cases = build_cases()
    tasks = make_tasks(cases)
    assert len(tasks) == 56
    schema = json.loads(SCHEMA.read_text())
    out.mkdir(parents=True, exist_ok=False)
    dump(out / "cases.json", cases)
    dump(out / "tasks.json", tasks)
    dump(out / "schema.json", schema)
    (out / "policy.txt").write_text(SCOPE_POLICY, encoding="utf-8")
    dump(out / "manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "candidate": PROMPT_VERSION,
        "model": CLASSIFIER_MODEL_NAME, "temperature": 0, "seed": 42, "max_output_tokens": 1024,
        "max_api_attempts": 56, "http_attempts": 1, "retry": 0, "timeout_seconds": 45,
        "min_interval_seconds": 12.2, "max_wall_seconds": 1200, "max_estimated_usd": 0.60,
        "accounting_rates_per_million": {"input": 1.0, "output": 10.0},
        "accounting_note": "Conservative experiment accounting assumptions, not a verified provider tariff or billed amount.",
        "primary": "20 known expressions: both expressions must have correct label and render successfully per scenario",
        "gate": {"min_net_improved_scenarios": 1, "max_new_regressions": 0,
                 "max_new_unsafe_sufficient": 0, "all_candidate_diagnostic_factors_correct": True,
                 "all_candidate_repeat_cases_correct": True, "all_calls_complete": True},
        "scope": "Gate 1 classifier-only development mechanism; not production adoption or unseen evaluation",
        "excluded_ambiguous_scenarios": ["A01", "B01"], "repeat_ids": sorted(REPEAT_IDS),
        "gold_status": "Existing annotations reused; new diagnostic factors provisional, no user-approved adoption gold",
        "frozen_hashes": {n: sha(out / n) for n in ("cases.json", "tasks.json", "schema.json", "policy.txt")},
        "source_hashes": {n: sha(BASE_DIR / n) for n in SOURCE_FILES},
        "input_hashes": {str(p.relative_to(BASE_DIR)): sha(p) for p in [SOURCE / "challenge.json", SOURCE / "api_attempts.jsonl"]},
    })


def score(case, data):
    parsed = parse_classification_output(data)
    label = derive_label(parsed.factors)
    factors = asdict(parsed.factors)
    factors_ok = all(factors[k] == v for k, v in case["expected_factors"].items())
    display_error = None
    try:
        p = case["payload"]
        answer = parse_answer_output(p["generated_answer"])
        validate_answer_evidence(answer, {UUID(e["element_id"]) for e in p["retrieved_evidence"]})
        render_display_answer(answer, parsed)
    except Exception as exc:
        display_error = type(exc).__name__
    correct = (label == case["expected_label"] and display_error is None) if case["kind"] == "known_development" else factors_ok
    return {"label": label, "factors": factors, "correct": correct,
            "factors_ok": factors_ok, "display_error": display_error,
            "unsafe_sufficient": case["expected_label"] in {"判断要", "文書不足"} and label == "根拠十分"}


def summarize(cases, tasks, records, stop_reason, spent):
    by_key = {(r["case_id"], r["arm"], r["repetition"]): r for r in records}
    groups = {}
    for case in cases:
        if case["kind"] == "known_development":
            groups.setdefault(case["scenario_id"], []).append(case["id"])
    pairs = {}
    for sid, ids in groups.items():
        pairs[sid] = {arm: all(by_key.get((cid, arm, 1), {}).get("correct", False) for cid in ids) for arm in ("baseline", "candidate")}
    improved = [s for s, p in pairs.items() if p["candidate"] and not p["baseline"]]
    regressed = [s for s, p in pairs.items() if p["baseline"] and not p["candidate"]]
    expr_regressions = [c["id"] for c in cases if c["kind"] == "known_development"
                        and by_key.get((c["id"], "baseline", 1), {}).get("correct", False)
                        and not by_key.get((c["id"], "candidate", 1), {}).get("correct", False)]
    diag_ok = all(by_key.get((c["id"], "candidate", 1), {}).get("correct", False) for c in cases if c["kind"] == "diagnostic_control")
    repeats_ok = all(by_key.get((cid, "candidate", rep), {}).get("correct", False) for cid in REPEAT_IDS for rep in (1, 2))
    unsafe = [r["case_id"] for r in records if r["arm"] == "candidate" and r.get("unsafe_sufficient")]
    complete = len(records) == len(tasks) and all(r.get("error") is None for r in records)
    gate = complete and len(improved) - len(regressed) >= 1 and not expr_regressions and not unsafe and diag_ok and repeats_ok
    return {"stop_reason": stop_reason, "completed_attempts": len(records), "planned_attempts": len(tasks),
            "complete_without_errors": complete, "paired_scenarios": pairs,
            "improved_scenarios": improved, "regressed_scenarios": regressed,
            "regressed_expressions": expr_regressions, "candidate_unsafe_sufficient": unsafe,
            "candidate_diagnostics_pass": diag_ok, "candidate_repeats_pass": repeats_ok,
            "gate1_pass": gate, "estimated_accounting_usd": spent,
            "errors": dict(Counter(r["error"] for r in records if r.get("error"))),
            "adoption": "not evaluated; gate1 only"}


def run(out):
    from google import genai
    from google.genai import types as gt
    from config import GOOGLE_API_KEY
    from src.llm_provider import _gemini_compatible_schema

    m = json.loads((out / "manifest.json").read_text())
    for name, expected in m["frozen_hashes"].items():
        if sha(out / name) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    for name, expected in m["source_hashes"].items():
        if sha(BASE_DIR / name) != expected:
            raise ValueError(f"Source changed: {name}")
    cases = json.loads((out / "cases.json").read_text())
    tasks = json.loads((out / "tasks.json").read_text())
    schema = json.loads((out / "schema.json").read_text())
    by_id = {c["id"]: c for c in cases}
    records = []
    spent = 0.0
    stop = "COMPLETED"
    start, last = time.monotonic(), None
    # Claim the run before creating the client; prevents repeated billing by rerun.
    with (out / "records.jsonl").open("x", encoding="utf-8") as stream:
        client = genai.Client(api_key=GOOGLE_API_KEY, http_options=gt.HttpOptions(
            timeout=45000, retry_options=gt.HttpRetryOptions(attempts=1)))
        for index, task in enumerate(tasks):
            if last is not None:
                time.sleep(max(0, m["min_interval_seconds"] - (time.monotonic() - last)))
            reserve = (len(task["prompt"].encode()) + len(json.dumps(schema).encode()) + 3000) / 1e6 + m["max_output_tokens"] * 10 / 1e6
            if index >= m["max_api_attempts"] or spent + reserve > m["max_estimated_usd"]:
                stop = "BUDGET_LIMIT"
                break
            if time.monotonic() - start + m["timeout_seconds"] > m["max_wall_seconds"]:
                stop = "WALL_LIMIT"
                break
            last = time.monotonic()
            row = {k: v for k, v in task.items() if k != "prompt"}
            row.update(index=index, started_at_utc=datetime.now(timezone.utc).isoformat(), error=None)
            try:
                response = client.models.generate_content(model=m["model"], contents=task["prompt"], config=gt.GenerateContentConfig(
                    temperature=0, seed=42, max_output_tokens=m["max_output_tokens"],
                    response_mime_type="application/json", response_json_schema=_gemini_compatible_schema(schema)))
                row.update(raw_text=response.text, model_version=response.model_version,
                           usage=response.usage_metadata.model_dump() if response.usage_metadata else {})
                usage = row["usage"]
                cost = ((usage.get("prompt_token_count") or 0) + 10 * ((usage.get("candidates_token_count") or 0) + (usage.get("thoughts_token_count") or 0))) / 1e6
                row["estimated_accounting_usd"] = cost if usage else reserve
                spent += row["estimated_accounting_usd"]
                if not usage:
                    raise ValueError("MISSING_USAGE")
                data = json.loads(response.text)
                row["data"] = data
                jsonschema.Draft202012Validator(schema).validate(data)
                row.update(score(by_id[task["case_id"]], data))
            except Exception as exc:
                row["error"] = type(exc).__name__
                row["error_message"] = str(exc).replace(GOOGLE_API_KEY or "__NO_KEY__", "[redacted]")[:1500]
                if "estimated_accounting_usd" not in row:
                    row["estimated_accounting_usd"] = reserve
                    spent += reserve
                stop = "FAIL_FAST_ERROR"
            row["latency_seconds"] = round(time.monotonic() - last, 3)
            records.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            dump(out / "summary.json", summarize(cases, tasks, records, "RUNNING" if not row["error"] else stop, spent))
            print(f"{index + 1}/{len(tasks)} {task['case_id']} {task['arm']} label={row.get('label')} correct={row.get('correct')} error={row['error']}", flush=True)
            if row["error"]:
                break
    dump(out / "summary.json", summarize(cases, tasks, records, stop, spent))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.run:
        run(args.output_dir)
    else:
        prepare(args.output_dir)
