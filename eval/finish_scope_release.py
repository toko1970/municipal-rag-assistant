"""One final bounded continuation after the recorded 503; no in-run retries."""

import argparse
import json
from pathlib import Path

from eval.continue_scope_release import verify, records, read, key
from eval.evaluate_scope_release import run, dump, sha, summarize


def prepare(root, previous, out):
    manifest = verify(root)
    prior = records(root / "records.jsonl") + records(previous / "records.jsonl")
    completed = {key(r) for r in prior if not r.get("api_error")}
    tasks = [t for t in read(root / "tasks.json") if key(t) not in completed]
    out.mkdir(parents=True, exist_ok=False)
    for name in ("cases.json", "schemas.json"):
        dump(out / name, read(root / name))
    dump(out / "tasks.json", tasks)
    manifest.update(
        stage="gate1_final_bounded_503_continuation",
        original=str(root.resolve()),
        previous=str(previous.resolve()),
        max_attempts=len(tasks),
        max_accounting_usd=0.8 - sum(r["accounting_usd"] for r in prior),
        retry_note="One explicit additional continuation after 503, authorized task continuation; no further automatic restart if this run fails. Original retry0 runs preserved.",
        frozen_hashes={
            n: sha(out / n) for n in ("cases.json", "schemas.json", "tasks.json")
        },
        prior_records_hashes={
            str((p / "records.jsonl").resolve()): sha(p / "records.jsonl")
            for p in (root, previous)
        },
    )
    manifest["source_hashes"]["eval/finish_scope_release.py"] = sha(Path(__file__))
    dump(out / "manifest.json", manifest)


def execute(out):
    manifest = read(out / "manifest.json")
    for name, h in manifest["prior_records_hashes"].items():
        if sha(Path(name)) != h:
            raise ValueError("Prior record changed")
    run(out)
    root = Path(manifest["original"])
    attempts = (
        records(root / "records.jsonl")
        + records(Path(manifest["previous"]) / "records.jsonl")
        + records(out / "records.jsonl")
    )
    selected = [r for r in attempts if not r.get("api_error")]
    if len({key(r) for r in selected}) != len(selected):
        raise ValueError("Duplicate response")
    summary = summarize(
        read(root / "cases.json"),
        read(root / "tasks.json"),
        selected,
        read(out / "summary.json")["stop"],
        sum(r["accounting_usd"] for r in attempts),
    )
    summary.update(
        total_api_attempts=len(attempts),
        provider_errors=sum(bool(r.get("api_error")) for r in attempts),
        completed_model_responses=len(selected),
        model_versions=sorted({r.get("model_version", "unknown") for r in selected}),
        automatic_restarts_remaining=0,
        note="Frozen cross-day paired classifier evaluation; previous API failures retained separately. Not holdout or full pipeline.",
    )
    dump(out / "combined_records.json", selected)
    dump(out / "combined_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path)
    p.add_argument("--previous", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--run", action="store_true")
    args = p.parse_args()
    execute(args.output_dir) if args.run else prepare(
        args.root, args.previous, args.output_dir
    )
