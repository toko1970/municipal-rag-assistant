"""Resume frozen evaluation tasks without overwriting earlier evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, CLASSIFIER_MODEL_NAME
from eval.evaluate_scope_release import dump, run, sha, summarize


def read(path):
    return json.loads(path.read_text())


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def key(row):
    return row["case_id"], row["arm"], row["repetition"]


def verify(original):
    manifest = read(original / "manifest.json")
    for name, expected in manifest["source_hashes"].items():
        if sha(BASE_DIR / name) != expected:
            raise ValueError(f"Frozen source changed: {name}")
    for name, expected in manifest["frozen_hashes"].items():
        if sha(original / name) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    if CLASSIFIER_MODEL_NAME != manifest["model"]:
        raise ValueError("Configured model changed")
    return manifest


def prepare(original, out):
    manifest = verify(original)
    prior = records(original / "records.jsonl")
    complete = {key(r) for r in prior if not r.get("api_error")}
    pending = [t for t in read(original / "tasks.json") if key(t) not in complete]
    if pending != read(original / "pending_tasks.json"):
        raise ValueError("Pending tasks mismatch")
    out.mkdir(parents=True, exist_ok=False)
    for name in ("cases.json", "schemas.json"):
        shutil.copyfile(original / name, out / name)
    dump(out / "tasks.json", pending)
    manifest.update(
        stage="gate1_frozen_continuation",
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        max_attempts=len(pending),
        max_accounting_usd=manifest["max_accounting_usd"]
        - sum(r["accounting_usd"] for r in prior),
        continuation_of=str(original.resolve()),
        prior_responses=len(complete),
        prior_attempts=len(prior),
        max_total_attempts=len(prior) + len(pending),
        retry_note="One explicit cross-day retry of the quota-failed task; no SDK or in-run retry",
        predecessor_records_sha256=sha(original / "records.jsonl"),
        frozen_hashes={
            n: sha(out / n) for n in ("cases.json", "schemas.json", "tasks.json")
        },
    )
    manifest["source_hashes"]["eval/continue_scope_release.py"] = sha(Path(__file__))
    dump(out / "manifest.json", manifest)


def execute(out):
    manifest = read(out / "manifest.json")
    original = Path(manifest["continuation_of"])
    verify(original)
    if sha(original / "records.jsonl") != manifest["predecessor_records_sha256"]:
        raise ValueError("Predecessor results changed")
    run(out)
    prior = records(original / "records.jsonl")
    current = records(out / "records.jsonl")
    selected = [r for r in prior if not r.get("api_error")] + [
        r for r in current if not r.get("api_error")
    ]
    if len({key(r) for r in selected}) != len(selected):
        raise ValueError("Duplicate completed task")
    all_attempts = prior + current
    summary = summarize(
        read(original / "cases.json"),
        read(original / "tasks.json"),
        selected,
        read(out / "summary.json")["stop"],
        sum(r["accounting_usd"] for r in all_attempts),
    )
    summary.update(
        total_api_attempts=len(all_attempts),
        provider_errors=sum(bool(r.get("api_error")) for r in all_attempts),
        completed_model_responses=len(selected),
        model_versions=sorted({r.get("model_version", "unknown") for r in selected}),
        note="Cross-day continuation; prior provider failure retained, not scored as a semantic response. This is not end-to-end or holdout evaluation.",
    )
    dump(out / "combined_records.json", selected)
    dump(out / "combined_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    execute(args.output_dir) if args.run else prepare(args.original, args.output_dir)
