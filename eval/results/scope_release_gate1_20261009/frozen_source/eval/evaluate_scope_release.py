"""Paired fixed-input gate for the deployable scope contract; no gold in prompts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from uuid import UUID

from config import BASE_DIR, CLASSIFIER_MODEL_NAME
from eval.evaluate_classification_scope_policy import build_cases, dump, make_tasks, sha
from src.answering import (
    parse_answer_output,
    parse_classification_output,
    render_display_answer,
    validate_answer_evidence,
)
from src.classification_scope_contract import (
    PROMPT_VERSION,
    build_scope_prompt,
    decide_scope_answer,
    scope_schema,
)
from src.query_service import build_classification_prompt_v1_from_payload


def prepare(out):
    cases = build_cases()
    tasks = make_tasks(cases)
    by_id = {c["id"]: c for c in cases}
    schemas = {
        "baseline": json.loads(
            (
                BASE_DIR / "design/schemas/classification-output-v1.schema.json"
            ).read_text()
        ),
        "candidate": scope_schema(),
    }
    for task in tasks:
        p = by_id[task["case_id"]]["payload"]
        builder = (
            build_scope_prompt
            if task["arm"] == "candidate"
            else build_classification_prompt_v1_from_payload
        )
        task["prompt"] = builder(
            p["question"], p["retrieved_evidence"], p["generated_answer"]
        )
        task["prompt_sha256"] = hashlib.sha256(task["prompt"].encode()).hexdigest()
    out.mkdir(parents=True, exist_ok=False)
    dump(out / "cases.json", cases)
    dump(out / "tasks.json", tasks)
    dump(out / "schemas.json", schemas)
    sources = [
        "src/classification_scope_contract.py",
        "src/query_service.py",
        "src/answering.py",
        "src/rag_v2.py",
        "eval/evaluate_scope_release.py",
        "eval/evaluate_classification_scope_policy.py",
        "design/schemas/classification-scope-v2.schema.json",
        "app.py",
    ]
    dump(
        out / "manifest.json",
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "stage": "gate1_known_fixed_inputs",
            "candidate": PROMPT_VERSION,
            "model": CLASSIFIER_MODEL_NAME,
            "temperature": 0,
            "seed": 42,
            "max_output_tokens": 4096,
            "max_attempts": 56,
            "retry": 0,
            "interval_seconds": 12.2,
            "max_wall_seconds": 1500,
            "max_accounting_usd": 0.80,
            "rates_per_million": {"input": 1, "output": 10},
            "rates_note": "Budget assumptions, not provider tariff",
            "gate": "Complete; known scenario net improvement >=1; no new expression regression; candidate unsafe sufficient 0; all diagnostic and repeat cases correct.",
            "diagnostics": "D01=policy judgment, D02=version conflict, D03/D04=GENERATION_INCOMPLETE with no label or claims",
            "gold_status": "Known gold preserved; diagnostic generation failure is separately specified by the new contract",
            "frozen_hashes": {
                n: sha(out / n) for n in ("cases.json", "tasks.json", "schemas.json")
            },
            "source_hashes": {n: sha(BASE_DIR / n) for n in sources},
        },
    )


def score(case, arm, data):
    p = case["payload"]
    answer = parse_answer_output(p["generated_answer"])
    evidence_ids = {e["element_id"] for e in p["retrieved_evidence"]}
    validate_answer_evidence(answer, {UUID(e) for e in evidence_ids})
    if arm == "candidate":
        display = decide_scope_answer(data, answer, evidence_ids)
        review_types = {r["type"] for t in data["targets"] for r in t["reviews"]}
    else:
        cls = parse_classification_output(data)
        review_types = {
            name
            for name, yes in [
                ("case_fact", cls.factors.requires_case_facts),
                ("policy_judgment", cls.factors.requires_policy_judgment),
                ("version_conflict", cls.factors.version_conflict),
            ]
            if yes
        }
        display = render_display_answer(answer, cls)
    if case["id"] in {"D03", "D04"}:
        correct = (
            display.status == "GENERATION_INCOMPLETE"
            and display.label is None
            and not display.visible_claims
        )
    elif case["kind"] == "diagnostic_control":
        expected = {"policy_judgment"} if case["id"] == "D01" else {"version_conflict"}
        correct = (
            display.status == "SUCCESS"
            and display.label == "判断要"
            and review_types == expected
        )
    else:
        correct = (
            display.status == "SUCCESS" and display.label == case["expected_label"]
        )
    return {
        "status": display.status,
        "label": display.label,
        "answer": display.text,
        "visible_claims": [c.claim_id for c in display.visible_claims],
        "review_types": sorted(review_types),
        "correct": correct,
        "unsafe_sufficient": display.label == "根拠十分"
        and case["expected_label"] in {"判断要", "文書不足"},
    }


def summarize(cases, tasks, records, stop, spent):
    by_key = {(r["case_id"], r["arm"], r["repetition"]): r for r in records}
    groups = {}
    for c in cases:
        if c["kind"] == "known_development":
            groups.setdefault(c["scenario_id"], []).append(c["id"])
    pairs = {
        sid: {
            arm: all(by_key.get((cid, arm, 1), {}).get("correct", False) for cid in ids)
            for arm in ("baseline", "candidate")
        }
        for sid, ids in groups.items()
    }
    improved = [sid for sid, p in pairs.items() if p["candidate"] and not p["baseline"]]
    regressed = [
        sid for sid, p in pairs.items() if p["baseline"] and not p["candidate"]
    ]
    expression_regressions = [
        c["id"]
        for c in cases
        if c["kind"] == "known_development"
        and by_key.get((c["id"], "baseline", 1), {}).get("correct", False)
        and not by_key.get((c["id"], "candidate", 1), {}).get("correct", False)
    ]
    diagnostics_ok = all(
        by_key.get((c["id"], "candidate", 1), {}).get("correct", False)
        for c in cases
        if c["kind"] == "diagnostic_control"
    )
    repeats_ok = all(
        by_key.get((t["case_id"], "candidate", rep), {}).get("correct", False)
        for t in tasks
        if t["arm"] == "candidate" and t["repetition"] == 2
        for rep in (1, 2)
    )
    unsafe = [
        r["case_id"]
        for r in records
        if r["arm"] == "candidate" and r.get("unsafe_sufficient")
    ]
    complete = len(records) == len(tasks) and not any(
        r.get("api_error") for r in records
    )
    return {
        "stop": stop,
        "attempts": len(records),
        "planned": len(tasks),
        "paired_scenarios": pairs,
        "improved": improved,
        "regressed": regressed,
        "expression_regressions": expression_regressions,
        "candidate_unsafe_sufficient": unsafe,
        "candidate_diagnostics_pass": diagnostics_ok,
        "candidate_repeats_pass": repeats_ok,
        "accounting_usd": spent,
        "known_expression_success": {
            arm: sum(
                r.get("correct", False)
                for r in records
                if r["arm"] == arm
                and r["repetition"] == 1
                and not r["case_id"].startswith("D")
            )
            for arm in ("baseline", "candidate")
        },
        "status_counts": dict(
            Counter(f"{r['arm']}:{r.get('status')}" for r in records)
        ),
        "gate1_pass": complete
        and len(improved) - len(regressed) >= 1
        and not expression_regressions
        and not unsafe
        and diagnostics_ok
        and repeats_ok,
        "production_adoption": "not evaluated",
    }


def run(out):
    from google import genai
    from google.genai import types as gt
    from config import GOOGLE_API_KEY
    from src.llm_provider import _gemini_compatible_schema

    manifest = json.loads((out / "manifest.json").read_text())
    for name, expected in manifest["frozen_hashes"].items():
        if sha(out / name) != expected:
            raise ValueError("Frozen inputs changed")
    for name, expected in manifest["source_hashes"].items():
        if sha(BASE_DIR / name) != expected:
            raise ValueError(f"Source changed: {name}")
    cases, tasks, schemas = [
        json.loads((out / n).read_text())
        for n in ("cases.json", "tasks.json", "schemas.json")
    ]
    by_id = {c["id"]: c for c in cases}
    spent, last, started, records, stop = 0.0, None, time.monotonic(), [], "COMPLETED"
    with (out / "records.jsonl").open("x", encoding="utf-8") as stream:
        client = genai.Client(
            api_key=GOOGLE_API_KEY,
            http_options=gt.HttpOptions(
                timeout=45000, retry_options=gt.HttpRetryOptions(attempts=1)
            ),
        )
        for index, task in enumerate(tasks):
            if last is not None:
                time.sleep(
                    max(0, manifest["interval_seconds"] - (time.monotonic() - last))
                )
            schema = schemas[task["arm"]]
            reserve = (
                len(task["prompt"].encode())
                + len(json.dumps(schema).encode())
                + 3000
                + 10 * manifest["max_output_tokens"]
            ) / 1e6
            if (
                index >= manifest["max_attempts"]
                or spent + reserve > manifest["max_accounting_usd"]
                or time.monotonic() - started + 45 > manifest["max_wall_seconds"]
            ):
                stop = "BUDGET_OR_WALL_LIMIT"
                break
            row = {k: v for k, v in task.items() if k != "prompt"}
            row.update(
                index=index,
                api_error=None,
                error=None,
                correct=False,
                status=None,
                started_at_utc=datetime.now(timezone.utc).isoformat(),
            )
            last = time.monotonic()
            try:
                response = client.models.generate_content(
                    model=manifest["model"],
                    contents=task["prompt"],
                    config=gt.GenerateContentConfig(
                        temperature=0,
                        seed=42,
                        max_output_tokens=manifest["max_output_tokens"],
                        response_mime_type="application/json",
                        response_json_schema=_gemini_compatible_schema(schema),
                    ),
                )
                row.update(
                    raw_text=response.text,
                    model_version=response.model_version,
                    usage=response.usage_metadata.model_dump()
                    if response.usage_metadata
                    else {},
                )
            except Exception as exc:
                row["api_error"] = type(exc).__name__
                row["error"] = str(exc).replace(
                    GOOGLE_API_KEY or "__NO_KEY__", "[redacted]"
                )[:1500]
                row["status"] = "PROVIDER_ERROR"
                stop = "PROVIDER_ERROR"
            usage = row.get("usage") or {}
            cost = (
                (
                    (usage.get("prompt_token_count") or 0)
                    + 10
                    * (
                        (usage.get("candidates_token_count") or 0)
                        + (usage.get("thoughts_token_count") or 0)
                    )
                )
                / 1e6
                if usage
                else reserve
            )
            row["accounting_usd"] = cost
            spent += cost
            if not row["api_error"]:
                try:
                    row["data"] = json.loads(row["raw_text"])
                    row.update(score(by_id[task["case_id"]], task["arm"], row["data"]))
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {str(exc)[:1000]}"
                    row["status"] = "PIPELINE_INCONSISTENCY"
                if not usage:
                    row["api_error"] = "MISSING_USAGE"
                    stop = "MISSING_USAGE"
            row["latency_seconds"] = round(time.monotonic() - last, 3)
            records.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            dump(
                out / "summary.json",
                summarize(
                    cases,
                    tasks,
                    records,
                    "RUNNING" if not row["api_error"] else stop,
                    spent,
                ),
            )
            print(
                f"{index + 1}/{len(tasks)} {task['case_id']} {task['arm']} {row['status']} correct={row['correct']}",
                flush=True,
            )
            if row["api_error"]:
                break
    dump(out / "summary.json", summarize(cases, tasks, records, stop, spent))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run(args.output_dir) if args.run else prepare(args.output_dir)
