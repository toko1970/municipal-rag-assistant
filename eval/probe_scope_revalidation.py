"""Four known mechanism probes, never holdout or full pipeline evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from uuid import UUID

from config import CLASSIFIER_MODEL_NAME
from src.answering import parse_answer_output
from src.classification_scope_contract import revalidate_resolved_answer, PROMPT_VERSION
from src.llm_provider import StructuredLLMResult

EID = "c55b0157-7719-41aa-a57e-2516327dac2b"


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def cases():
    rows = []
    for name, text, status, label in [
        ("correct_price", "2027年4月1日の単価は300円です。", "SUCCESS", "根拠十分"),
        (
            "stale_abstention",
            "200円と300円が競合するため、単価を確定できません。",
            "GENERATION_INCOMPLETE",
            None,
        ),
        ("old_price", "2027年4月1日の単価は200円です。", "GENERATION_INCOMPLETE", None),
        (
            "individual_review",
            "単価は300円ですが、この職員への支給には記録照合が必要です。",
            "SUCCESS",
            "判断要",
        ),
    ]:
        review = {
            "type": "version_conflict",
            "reason": "適用単価の版が競合",
            "evidence_ids": [EID],
        }
        target = {
            "target": "適用単価",
            "intent": "general_rule",
            "evidence_sufficient": True,
            "evidence_ids": [EID],
            "claim_ids": ["claim-1"],
            "claim_support": "supported",
            "answer_complete": True,
            "reviews": [review],
        }
        question = "2027年4月1日の適用単価はいくらですか？"
        if name == "individual_review":
            question = "2027年4月1日にこの職員へ単価300円で支給を確定できますか？記録は未照合です。"
            target.update(target="この職員への支給確定", intent="individual_decision")
            target["reviews"].append(
                {
                    "type": "case_fact",
                    "reason": "個別記録が未照合",
                    "evidence_ids": [EID],
                }
            )
        rows.append(
            {
                "id": name,
                "question": question,
                "evidence": [
                    {
                        "element_id": EID,
                        "content": "2026年12月31日までは単価200円。2027年1月1日から単価300円を適用する。職員への支給確定には個別記録の照合が必要。",
                    }
                ],
                "answer_data": {
                    "schema_version": "1.0",
                    "claims": [
                        {
                            "claim_id": "claim-1",
                            "ordinal": 1,
                            "text": text,
                            "evidence_element_ids": [EID],
                            "evidence_kind": "text",
                        }
                    ],
                    "missing_conditions": [],
                },
                "original": {
                    "schema_version": "scope-2.0",
                    "confidence": 0.9,
                    "targets": [target],
                },
                "resolution_data": {
                    "schema_version": "1.0",
                    "status": "SUCCESS",
                    "version_conflict": False,
                    "resolution_basis": "question_date",
                    "evidence_element_ids": [EID],
                    "confidence": 0.95,
                    "error_code": None,
                },
                "expected_status": status,
                "expected_label": label,
            }
        )
    return rows


class Logger:
    def __init__(self):
        self.events = []

    def record_classification_attempt(self, request_id, **kwargs):
        self.events.append({"request_id": str(request_id), **kwargs})


def run(out):
    from google import genai
    from google.genai import types
    from config import GOOGLE_API_KEY
    from src.llm_provider import _gemini_compatible_schema

    out.mkdir(parents=True, exist_ok=False)
    source = [
        "src/classification_scope_contract.py",
        "src/query_service.py",
        "eval/probe_scope_revalidation.py",
    ]
    rows = cases()
    save(out / "cases.json", rows)
    save(
        out / "manifest.json",
        {
            "candidate": PROMPT_VERSION,
            "purpose": "known mechanism, not holdout",
            "model": CLASSIFIER_MODEL_NAME,
            "max_calls": 4,
            "max_accounting_usd": 0.40,
            "interval_seconds": 12.2,
            "timeout_seconds": 45,
            "retry": 0,
            "max_output_tokens": 4096,
            "temperature": 0,
            "seed": 42,
            "gate": "all four expected status/labels, no claims on failure",
            "rates_note": "Input1/output10 USD per million budget assumptions, not billing rates",
            "source_hashes": {
                f: hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in source
            },
            "cases_sha256": hashlib.sha256(
                (out / "cases.json").read_bytes()
            ).hexdigest(),
        },
    )
    client = genai.Client(
        api_key=GOOGLE_API_KEY,
        http_options=types.HttpOptions(
            timeout=45000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    )

    class Provider:
        provider_name = "gemini"
        model = CLASSIFIER_MODEL_NAME
        spent = 0.0
        last = None
        calls = 0
        stop = False

        def generate_structured(self, prompt, schema):
            if self.calls >= 4 or self.stop:
                raise RuntimeError("PROBE_STOPPED")
            reserve = (
                len(prompt.encode()) + len(json.dumps(schema).encode()) + 3000 + 40960
            ) / 1e6
            if self.spent + reserve > 0.4:
                self.stop = True
                raise RuntimeError("BUDGET_LIMIT")
            if self.last is not None:
                time.sleep(max(0, 12.2 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            self.calls += 1
            save(
                out / f"request_{self.calls}.json",
                {"prompt": prompt, "schema": schema, "reserve": reserve},
            )
            self.spent += reserve
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        seed=42,
                        max_output_tokens=4096,
                        response_mime_type="application/json",
                        response_json_schema=_gemini_compatible_schema(schema),
                    ),
                )
            except Exception:
                self.stop = True
                raise
            usage = response.usage_metadata
            save(
                out / f"response_{self.calls}.json",
                {
                    "text": response.text,
                    "usage": usage.model_dump() if usage else None,
                    "model_version": response.model_version,
                },
            )
            if usage is None:
                self.stop = True
                raise ValueError("MISSING_USAGE")
            output = (usage.candidates_token_count or 0) + (
                usage.thoughts_token_count or 0
            )
            self.spent += (
                (usage.prompt_token_count or 0) + output * 10
            ) / 1e6 - reserve
            return StructuredLLMResult(
                "gemini",
                self.model,
                json.loads(response.text),
                input_tokens=usage.prompt_token_count or 0,
                output_tokens=output,
            )

    provider = Provider()
    results = []
    for row in rows:
        logger = Logger()
        started = time.monotonic()
        display, metadata = revalidate_resolved_answer(
            **{
                k: row[k]
                for k in (
                    "question",
                    "evidence",
                    "answer_data",
                    "original",
                    "resolution_data",
                )
            },
            answer=parse_answer_output(row["answer_data"]),
            classifier=provider,
            event_logger=logger,
            request_id=UUID(EID),
            confidence_threshold=0.8,
        )
        ok = (
            metadata["error_summary"] is None
            and display.status == row["expected_status"]
            and display.label == row["expected_label"]
            and (display.status == "SUCCESS" or not display.visible_claims)
        )
        results.append(
            {
                "id": row["id"],
                "correct": ok,
                "status": display.status,
                "label": display.label,
                "text": display.text,
                "metadata": metadata,
                "events": logger.events,
                "latency_seconds": time.monotonic() - started,
            }
        )
        save(out / "results.json", results)
        save(
            out / "summary.json",
            {
                "calls": provider.calls,
                "completed": len(results),
                "planned": 4,
                "passed": sum(r["correct"] for r in results),
                "all_pass": len(results) == 4
                and all(r["correct"] for r in results)
                and not provider.stop,
                "accounting_usd": provider.spent,
                "provider_stopped": provider.stop,
                "holdout": "not run",
                "deployment": "not performed",
            },
        )
        print(row["id"], display.status, display.label, ok, flush=True)
        if provider.stop:
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    run(parser.parse_args().output_dir)
