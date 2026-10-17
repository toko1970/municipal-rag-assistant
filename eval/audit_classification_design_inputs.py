"""Offline diagnosis of classification design and actual saved model inputs.

Reads opened development artifacts only; does not invoke a provider or alter gold.
Usage: .venv/bin/python eval/audit_classification_design_inputs.py --output-dir PATH
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.answering import ClassificationFactors, derive_label
from src.query_service import build_classification_prompt_v1_from_payload

SOURCE = ROOT / "eval/results/generalization_completion_20261009/classification"


def read(name):
    text = (SOURCE / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line] if name.endswith(".jsonl") else json.loads(text)


def key(row):
    return tuple(row[k] for k in ("row_id", "evidence_mode", "arm", "repetition"))


def audit():
    records = read("service_records.jsonl")
    reviews = read("semantic_review.jsonl")
    attempts = read("api_attempts.jsonl")
    challenge = {r["id"]: r for r in read("challenge.json")}
    corpus = {r["element_id"]: r for r in read("corpus.json")}
    services = {key(r): r for r in records}
    annotations = {key(r): r for r in reviews}
    assert len(services) == len(records) == len(annotations) == len(reviews) == 88
    assert services.keys() == annotations.keys()
    for k, r in services.items():
        assert r["index"] == annotations[k]["index"]
        assert r["scenario_id"] == annotations[k]["scenario_id"]

    inputs = []
    for a in attempts:
        assert hashlib.sha256(a["prompt"].encode()).hexdigest() == a["prompt_sha256"]
        if a["phase"] not in ("v1_classification", "v2_classification"):
            continue
        r = services[key(a["task"])]
        payload = json.loads(a["prompt"].split("判定対象: ", 1)[1])
        evidence = payload["retrieved_evidence"]
        assert payload["question"] == r["question"]
        assert [e["element_id"] for e in evidence] == r["retrieved_ids"]
        assert all(e["content"] == corpus[e["element_id"]]["content"] for e in evidence)
        generation = next(e["response_data"] for e in r["events"] if e["type"] == "generation")
        # All saved v1 records in this campaign use answer-output-v1 unchanged.
        copied = payload["generated_answer"] == generation
        if r["arm"] == "v1":
            assert copied
            assert a["prompt"] == build_classification_prompt_v1_from_payload(
                payload["question"], evidence, generation
            )
            assert set(payload) == {"question", "retrieved_evidence", "generated_answer"}
        inputs.append({
            "key": list(key(r)), "evidence_count": len(evidence),
            "evidence_characters": sum(len(e["content"]) for e in evidence),
            "payload_keys": sorted(payload), "generation_exact_copy": copied,
            "prompt_characters": len(a["prompt"]),
        })

    paired = {}
    for mode in ("oracle", "retrieved"):
        by_scenario = {}
        for arm in ("v1", "v2"):
            selected = [r for r in reviews if r["evidence_mode"] == mode and r["arm"] == arm and r["repetition"] == 1]
            for sid in sorted({r["scenario_id"] for r in selected}):
                group = [r for r in selected if r["scenario_id"] == sid]
                assert len(group) == 2
                by_scenario.setdefault(sid, {})[arm] = all(r["manual_final_composite"] for r in group)
        counts = Counter("both" if v["v1"] and v["v2"] else "v1_only" if v["v1"] else "v2_only" if v["v2"] else "neither" for v in by_scenario.values())
        paired[mode] = {"scenario_results": by_scenario, "counts": dict(counts)}

    errors = []
    for r in records:
        k = key(r)
        gold = annotations[k]
        if r["arm"] != "v1" or r["evidence_mode"] != "oracle" or r["repetition"] != 1:
            continue
        result = r.get("result") or {}
        if gold["expected_label"] == "根拠十分" and result.get("answer_label") == "判断要":
            gen = next(e["response_data"] for e in r["events"] if e["type"] == "generation")
            cls = next(e for e in r["events"] if e["type"] == "classification" and e["prompt_version"] == "answer-classification-v1")
            errors.append({"row_id": r["row_id"], "question": r["question"],
                           "missing_conditions": gen["missing_conditions"],
                           "factors": cls["factors"], "confidence": cls["confidence"],
                           "ambiguous_scenario": r["scenario_id"] in {"A01", "B01"}})

    comparisons = []
    for r in records:
        if r["evidence_mode"] != "retrieved" or r["repetition"] != 1:
            continue
        base = services[(r["row_id"], "oracle", r["arm"], 1)]
        required = set(challenge[r["row_id"]]["oracle_evidence_ids"])
        def generation(row):
            return next((e.get("response_data") for e in row["events"] if e["type"] == "generation"), None)
        def result(row):
            value = row.get("result") or {}
            return [row["status"], value.get("answer_label"), value.get("invariant_code")]
        comparisons.append({"row_id": r["row_id"], "arm": r["arm"],
                            "all_required_docs_present": required <= set(r["retrieved_doc_keys"]),
                            "oracle_docs": base["retrieved_doc_keys"], "retrieved_docs": r["retrieved_doc_keys"],
                            "generation_equal": generation(base) == generation(r),
                            "oracle_result": result(base), "retrieved_result": result(r)})

    # Deterministic mechanism probes, not model accuracy measurements.
    probes = []
    for name, values in [
        ("supported_without_review", (True, True, False, False, False)),
        ("supported_with_case_fact", (True, True, True, False, False)),
        ("no_rule_without_review", (False, False, False, False, False)),
        ("no_rule_with_case_fact", (False, False, True, False, False)),
        ("rule_present_but_unsupported_answer", (True, False, False, False, False)),
        ("unsupported_answer_with_case_fact", (True, False, True, False, False)),
    ]:
        factors = ClassificationFactors(*values)
        probes.append({"case": name, "factors": vars(factors), "v1_label": derive_label(factors)})

    schema = json.loads((ROOT / "design/schemas/classification-output-v1.schema.json").read_text())
    paths = [SOURCE / n for n in ("service_records.jsonl", "api_attempts.jsonl", "semantic_review.jsonl", "challenge.json", "corpus.json")]
    paths += [ROOT / n for n in ("eval/audit_classification_design_inputs.py", "src/query_service.py", "src/query_service_v2.py", "src/answering.py", "src/classification_contract_v2.py", "src/rag_v2.py", "src/llm_provider.py", "config.py", "design/CLASSIFICATION_RUBRIC_V2.md", "design/schemas/classification-output-v1.schema.json")]
    return {
        "scope": "offline saved-input audit and current-code deterministic probes; no new LLM evaluation",
        "new_api_calls": 0, "review_source": "existing semantic annotations; no fresh blind annotation",
        "service_count": len(records), "saved_api_attempt_count": len(attempts),
        "classification_inputs_audited": len(inputs),
        "classification_inputs_by_arm": dict(Counter(x["key"][2] for x in inputs)),
        "full_evidence_content_and_order_verified": True,
        "v1_factor_schema": schema["$defs"]["factors"]["properties"],
        "paired_recount": paired, "oracle_v1_overdeferral": errors,
        "overdeferral_with_empty_generated_conditions": sum(not r["missing_conditions"] for r in errors),
        "oracle_retrieved_comparisons": comparisons, "decision_probes": probes,
        "input_audit": inputs,
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = audit()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("service_count", "classification_inputs_audited", "classification_inputs_by_arm", "overdeferral_with_empty_generated_conditions", "paired_recount", "decision_probes")}, ensure_ascii=False, indent=2))
