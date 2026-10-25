"""Bounded exploratory experiment; uses frozen 2026-09-29 evidence, never changes product code."""

from __future__ import annotations
import ast
import collections
import hashlib
import json
import re
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "eval/results/failure_hypotheses_verification_20261009"
if "--output-dir" in sys.argv:
    OUT = Path(sys.argv[sys.argv.index("--output-dir") + 1]).resolve()
COMMIT = "5d1ecc50985db681cfa71bddc6cbfcfa99480e40"


def write(n, x):
    (OUT / n).write_text(json.dumps(x, ensure_ascii=False, indent=2) + "\n")


def rows(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def old(p):
    return subprocess.check_output(
        ["git", "show", f"{COMMIT}:{p}"], cwd=ROOT, text=True
    )


def key(r):
    return r["scenario_id"] + "/" + r["variant_type"]


def load_old():
    m = types.ModuleType("historical_answering")
    sys.modules[m.__name__] = m
    exec(old("src/answering.py"), m.__dict__)
    return m


def main():
    if (OUT / "api_records.jsonl").exists():
        raise RuntimeError(
            "Existing API records are immutable; use a fresh --output-dir or the offline analyzer."
        )
    import config
    from src.ingestion import build_markdown_elements
    from src.llm_provider import _gemini_compatible_schema

    OUT.mkdir(parents=True, exist_ok=True)
    preds_path = ROOT / "eval/results/text_holdout_v1_predictions_v10/predictions.jsonl"
    reviews_path = ROOT / "eval/results/text_holdout_v1_acceptance/content_review.jsonl"
    preds = {key(r): r for r in rows(preds_path)}
    reviews = rows(reviews_path)
    failures = [
        r
        for r in reviews
        if not all(r[k] for k in ["execution_ok", "classification_ok", "content_ok"])
    ]
    mismatches = [
        r for r in reviews if r["execution_ok"] and not r["classification_ok"]
    ]
    write(
        "historical_analysis.json",
        {
            "source_hashes": {
                str(p.relative_to(ROOT)): sha(p) for p in [preds_path, reviews_path]
            },
            "n": len(reviews),
            "success": len(reviews) - len(failures),
            "failure_count": len(failures),
            "failure_scenarios": len({r["scenario_id"] for r in failures}),
            "classification_mismatch_on_executed": len(mismatches),
            "executed": sum(r["execution_ok"] for r in reviews),
            "content_fail_executed": sum(
                r["execution_ok"] and not r["content_ok"] for r in reviews
            ),
            "error_count": sum(not r["execution_ok"] for r in reviews),
            "classification_confusion": dict(
                collections.Counter(
                    r["expected_label"] + " -> " + str(r["predicted_label"])
                    for r in mismatches
                )
            ),
            "failures": failures,
            "note": "Reanalysis of saved human scoring; not fresh 100-expression model regression.",
        },
    )
    m = load_old()
    cl = m.AnswerClaim("claim-1", 1, "支持された主張", (), "text")
    fc = m.ClassificationFactors(True, True, False, False, False)
    cr = m.ClassificationResult(fc, 1.0)
    local = []
    for name, cs, ms, want in [
        ("no_claims", (), (), True),
        ("unresolved_condition", (cl,), ("確認対象",), True),
        ("normal", (cl,), (), False),
    ]:
        try:
            m.render_display_answer(m.StructuredAnswer(cs, ms), cr)
            err = None
        except ValueError as e:
            err = str(e)
        local.append(
            {
                "case": name,
                "error": err,
                "expected_error": want,
                "passed": bool(err) == want,
            }
        )
    write(
        "display_contract_reproduction.json",
        {
            "commit": COMMIT,
            "source_sha256": hashlib.sha256(
                old("src/answering.py").encode()
            ).hexdigest(),
            "cases": local,
            "limitation": "Synthetic branch reproduction. Historical raw generation and classification not persisted on error, so TH014/TH026 branch attribution is unknown.",
        },
    )
    elements = {}
    manifest = json.loads((ROOT / "eval/text_holdout/public_manifest.json").read_text())
    for d in manifest["documents"]:
        p = ROOT / "eval/text_holdout/.sealed/documents" / f"{d['document_id']}.md"
        assert sha(p) == d["sha256"]
        elements.update({str(e.id): e for e in build_markdown_elements(p)})

    def ev(r):
        result = []
        for h in r["retrieved"]:
            e = elements[h["element_id"]]
            assert e.heading == h["heading"]
            result.append(
                {
                    "element_id": str(e.id),
                    "document_name": e.document_name,
                    "heading": e.heading,
                    "content": e.content,
                    "page_number": e.page_number,
                    "score": round(h["score"], 6),
                    "source": e.metadata.get("source", ""),
                    "element_type": e.element_type,
                    "visual_extraction": e.metadata.get("visual_extraction"),
                }
            )
        return result

    # Reuse exact historical prompt functions by AST extraction; no current routing is imported.
    tree = ast.parse(old("src/query_service.py"))
    wanted = {"_classification_payload", "build_classification_prompt_v1_from_payload"}
    ns = {"json": json}
    exec(
        compile(
            ast.Module(
                body=[
                    x
                    for x in tree.body
                    if isinstance(x, ast.FunctionDef) and x.name in wanted
                ],
                type_ignores=[],
            ),
            "historical_prompts",
            "exec",
        ),
        ns,
    )
    gp = "次の質問へ、取得根拠だけを使って回答してください。自由文の最終回答や分類は返さず、answer-output-v1のJSONだけを返してください。すべてのclaimにelement_idを引用してください。\n画像が添付される場合、visual_asset.attachment_indexが添付順（1始まり）です。\n"
    scope = "判定対象は質問が直接求める命題です。requires_case_factsはその命題への結論を変える未提示の個別事実がある場合だけtrueです。質問に明示済みの条件や質問の範囲外の支給条件を不足と見なしません。「現時点では確定できない」と根拠に従って回答することと、個別の支給可否を確定することを区別してください。requires_policy_judgmentはその命題に裁量が残る場合だけtrueです。\n"
    tasks = []

    def classify(cid, q, e, a, gold, origin):
        prompt = ns["build_classification_prompt_v1_from_payload"](q, e, a)
        for arm, extra in [("baseline", ""), ("scope_definition", scope)]:
            tasks.append(
                {
                    "id": cid,
                    "family": "classification",
                    "origin": origin,
                    "arm": arm,
                    "prompt": extra + prompt,
                    "expected_label": gold,
                    "question": q,
                    "evidence": e,
                    "answer": a,
                }
            )

    golds = {key(r): r["expected_label"] for r in reviews}
    for sid in ["TH025", "TH031", "TH022", "TH047"]:
        r = preds[sid + "/formal"]
        a = {
            "schema_version": "1.0",
            "claims": [dict(c, evidence_kind="text") for c in r["claims"]],
            "missing_conditions": [],
        }
        # Never use gold missing_conditions as model input. Grounded old displays prove empty; other labels use an explicit empty-condition control.
        a["missing_conditions"] = []
        classify(
            sid + "/formal",
            r["question"],
            ev(r),
            a,
            golds[key(r)],
            "historical_visible_claims_empty_missing_control",
        )
    eid = "00000000-0000-0000-0000-000000000001"
    e = [
        {
            "element_id": eid,
            "content": "架空の灯台研修助成は研修修了かつ在籍30日以上なら対象となる。研修未修了なら対象外。在籍日数が不明な場合、対象可否を確定できない。",
        }
    ]
    for cid, q, answer, gold, missing in [
        (
            "NEW-condition-known",
            "研修修了済み、在籍45日です。対象ですか。",
            "対象です。",
            "根拠十分",
            [],
        ),
        (
            "NEW-condition-missing",
            "研修修了済みです。対象ですか。",
            "在籍日数が不明のため確定できません。",
            "判断要",
            ["在籍日数"],
        ),
        (
            "NEW-answerability",
            "研修修了済みで在籍日数不明の場合、対象可否を今確定できますか。",
            "在籍日数が不明のため今は確定できません。",
            "根拠十分",
            [],
        ),
        (
            "NEW-explicit-negative",
            "研修未修了で在籍45日です。対象ですか。",
            "対象外です。",
            "根拠十分",
            [],
        ),
    ]:
        a = {
            "schema_version": "1.0",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "ordinal": 1,
                    "text": answer,
                    "evidence_element_ids": [eid],
                    "evidence_kind": "text",
                }
            ],
            "missing_conditions": missing,
        }
        classify(cid, q, e, a, gold, "new_exploratory_minimal_cases_not_sealed")
    for sid in ["TH011", "TH039"]:
        for variant in ["formal", "paraphrase_or_noisy"]:
            r = preds[sid + "/" + variant]
            e = ev(r)
            if sid == "TH011":
                single = (
                    r["question"]
                    .replace("補助額と提出期限", "提出期限")
                    .replace("補助いくら、いつまでに出す？", "いつまでに出す？")
                )
                date = "2027-10-30"
                clock = "noon"
            else:
                single = (
                    r["question"]
                    .replace("休務に数える時間と申込期限", "申込期限")
                    .replace(
                        "技能交換休務は何時間で、いつまでに申込む？",
                        "技能交換休務はいつまでに申込む？",
                    )
                )
                date = "2027-06-15"
                clock = "17"
            for arm, extra, q in [
                ("baseline", "", r["question"]),
                (
                    "explicit_date",
                    "期限を回答するときは、具体的な年月日と時刻まで答えてください。\n",
                    r["question"],
                ),
                (
                    "calculation_permission",
                    "質問にある日付と取得根拠の暦日規則を組み合わせた日付計算は許可されています。\n",
                    r["question"],
                ),
                ("deadline_only", "", single),
            ]:
                tasks.append(
                    {
                        "id": key(r),
                        "family": "deadline",
                        "origin": "historical_fixed_top8",
                        "arm": arm,
                        "prompt": extra
                        + gp
                        + f"質問: {q}\n取得根拠: "
                        + json.dumps(e, ensure_ascii=False),
                        "expected_date": date,
                        "expected_clock": clock,
                        "question": q,
                        "evidence": e,
                    }
                )
    r = preds["TH041/formal"]
    tasks.append(
        {
            "id": key(r),
            "family": "deadline_control",
            "origin": "historical_success_control",
            "arm": "baseline",
            "prompt": gp
            + f"質問: {r['question']}\n取得根拠: "
            + json.dumps(ev(r), ensure_ascii=False),
            "question": r["question"],
            "evidence": ev(r),
            "historical_answer": r["answer"],
        }
    )
    # Validate the old temporal wrapper contributes nothing on the selected questions.
    temporal = types.ModuleType("historical_temporal")
    sys.modules[temporal.__name__] = temporal
    temporal_source = old("src/temporal_evidence.py").replace(
        "from src.query_service import build_generation_prompt", ""
    )
    exec(temporal_source, temporal.__dict__)
    temporal_checks = [
        {
            "id": t["id"],
            "arm": t["arm"],
            "domains": sorted(temporal._question_domains(t["question"])),
        }
        for t in tasks
        if t["family"] != "classification"
    ]
    assert all(not r["domains"] for r in temporal_checks)
    write(
        "temporal_wrapper_check.json",
        {
            "commit": COMMIT,
            "checks": temporal_checks,
            "conclusion": "No question domain matched, so old temporal wrapper returns exact base prompt.",
        },
    )
    write("tasks.json", tasks)
    schemas = {
        k: json.loads(old("design/schemas/" + n))
        for k, n in [
            ("classification", "classification-output-v1.schema.json"),
            ("generation", "answer-output-v1.schema.json"),
        ]
    }
    write("schemas.json", schemas)
    write(
        "manifest.json",
        {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "historical_commit": COMMIT,
            "model": "gemini-3.1-flash-lite",
            "temperature": 0,
            "max_calls": 33,
            "max_campaign_calls_including_invalidated": 35,
            "review_revalidation_round": 1,
            "max_output_tokens": 1536,
            "max_estimated_cost_usd": 0.10,
            "pricing_assumption_usd_per_million": {"input": 0.25, "output": 1.5},
            "pricing_source": "existing repo eval/evaluate_visual_answers.py; not current billing verification",
            "max_retries": 0,
            "http_attempts": 1,
            "tasks_sha256": sha(OUT / "tasks.json"),
            "schemas_sha256": sha(OUT / "schemas.json"),
            "source_sha256": sha(Path(__file__)),
            "conditions": "Single run per condition. No inference of generalization or stable causal effect. Historical expected labels retained, not relabeled post hoc. Artificial answerability gold is explicitly question scoped.",
        },
    )
    if "--run" not in sys.argv:
        return
    if (OUT / "api_records.jsonl").exists():
        raise RuntimeError("Refuse overwrite API run")
    from google import genai
    from google.genai import types as gt

    client = genai.Client(
        api_key=config.GOOGLE_API_KEY,
        http_options=gt.HttpOptions(
            timeout=45000, retry_options=gt.HttpRetryOptions(attempts=1)
        ),
    )
    records = []
    spent = (
        json.loads((OUT / "invalidated_round0/invalidation.json").read_text())[
            "estimated_cost_usd"
        ]
        if (OUT / "invalidated_round0/invalidation.json").exists()
        else 0
    )
    for ix, t in enumerate(tasks):
        # Conservative byte upper bound on prompt input tokens plus schema and capped output; enforce before every call.
        reserve = (
            len(t["prompt"].encode()) + len(json.dumps(schemas).encode()) + 3000
        ) * 0.25 / 1e6 + 1536 * 1.5 / 1e6
        if spent + reserve > 0.10:
            break
        rec = {k: v for k, v in t.items() if k not in ["prompt", "evidence", "answer"]}
        rec["task_index"] = ix
        rec["prompt_sha256"] = hashlib.sha256(t["prompt"].encode()).hexdigest()
        try:
            resp = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=t["prompt"],
                config=gt.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=1536,
                    response_mime_type="application/json",
                    response_json_schema=_gemini_compatible_schema(
                        schemas[
                            "classification"
                            if t["family"] == "classification"
                            else "generation"
                        ]
                    ),
                ),
            )
            rec["raw_text"] = resp.text
            rec["data"] = json.loads(resp.text)
            u = resp.usage_metadata
            rec["usage"] = u.model_dump()
            rec["model_version"] = resp.model_version
            it = u.prompt_token_count or 0
            ot = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
            rec["estimated_cost_usd"] = (it * 0.25 + ot * 1.5) / 1e6
            spent += rec["estimated_cost_usd"]
            rec["error"] = None
            if t["family"] == "classification":
                c = m.parse_classification_output(rec["data"])
                rec["label"] = m.derive_label(c.factors)
                rec["correct"] = rec["label"] == t["expected_label"]
            else:
                a = m.parse_answer_output(rec["data"])
                m.validate_answer_evidence(
                    a, {__import__("uuid").UUID(x["element_id"]) for x in t["evidence"]}
                )
                text = "\n".join(c.text for c in a.claims)
                if t["family"] == "deadline":
                    year, mo, day = t["expected_date"].split("-")
                    pat = rf"{year}\s*(?:年|/|-)\s*0?{int(mo)}\s*(?:月|/|-)\s*0?{int(day)}(?:日)?"
                    rec["date_present"] = bool(re.search(pat, text))
                    rec["clock_present"] = bool(
                        re.search(
                            "正午|12時|12:00"
                            if t["expected_clock"] == "noon"
                            else "17時|17:00|午後5時",
                            text,
                        )
                    )
                    rec["correct"] = rec["date_present"] and rec["clock_present"]
        except Exception as ex:
            rec["error"] = type(ex).__name__
            rec["error_detail_redacted"] = (
                "Provider or validation error; no credentials logged."
            )
        records.append(rec)
        with (OUT / "api_records.jsonl").open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(ix + 1, t["id"], t["arm"], rec.get("correct"), rec["error"], flush=True)
        if rec["error"]:
            break
        time.sleep(5.1)
    summary = {
        "calls_attempted": len(records),
        "planned_calls": len(tasks),
        "completed": sum(r["error"] is None for r in records),
        "campaign_estimated_cost_usd": spent,
        "valid_run_estimated_cost_usd": sum(
            r.get("estimated_cost_usd", 0) for r in records
        ),
        "provider_error_count": sum(r["error"] is not None for r in records),
        "groups": {},
    }
    for family in ["classification", "deadline", "deadline_control"]:
        for arm in sorted({r["arm"] for r in records if r["family"] == family}):
            for origin in sorted(
                {r["origin"] for r in records if r["family"] == family}
            ):
                rr = [
                    r
                    for r in records
                    if r["family"] == family
                    and r["arm"] == arm
                    and r["origin"] == origin
                ]
                summary["groups"][family + "/" + origin + "/" + arm] = {
                    "n": len(rr),
                    "correct": sum(r.get("correct", False) for r in rr),
                    "errors": sum(r["error"] is not None for r in rr),
                }
    write("api_summary.json", summary)


if __name__ == "__main__":
    main()
