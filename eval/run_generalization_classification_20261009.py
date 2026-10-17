"""Frozen oracle/retrieved paired run of existing v1 and Question Contract v2."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval/results/generalization_completion_20261009/classification"
SOURCE_FILES = [
    "src/query_service.py", "src/query_service_v2.py", "src/classification_contract_v2.py",
    "src/answering.py", "src/llm_provider.py", "src/temporal_evidence.py",
    "design/schemas/answer-output-v1.schema.json", "design/schemas/classification-output-v1.schema.json",
    "design/schemas/question-contract-v1.schema.json", "design/schemas/answer-output-v3-candidate.schema.json",
    "design/schemas/classification-output-v2-candidate.schema.json",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prepare():
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["source_file_hashes"]:
        raise RuntimeError("Already prepared")
    corpus = json.loads((OUT / "corpus.json").read_text())
    rows = json.loads((OUT / "challenge.json").read_text())
    assert sha(OUT / "corpus.json") == manifest["corpus_sha256"]
    assert sha(OUT / "challenge.json") == manifest["challenge_sha256"]
    assert len(corpus) == 6 and len(rows) == 24
    tasks = []
    for row in rows:
        for arm in ("v1", "v2"):
            tasks.append({"row_id": row["id"], "scenario_id": row["scenario_id"],
                          "evidence_mode": "oracle", "arm": arm, "repetition": 1})
    for row in rows:
        if row["scenario_id"] in manifest["repeat_scenarios"]:
            for arm in ("v1", "v2"):
                tasks.append({"row_id": row["id"], "scenario_id": row["scenario_id"],
                              "evidence_mode": "oracle", "arm": arm, "repetition": 2})
    for row in rows:
        if row["scenario_id"] in manifest["retrieved_scenarios"]:
            for arm in ("v1", "v2"):
                tasks.append({"row_id": row["id"], "scenario_id": row["scenario_id"],
                              "evidence_mode": "retrieved", "arm": arm, "repetition": 1})
    assert len(tasks) == 88
    dump(OUT / "frozen_tasks.json", tasks)
    manifest["tasks_sha256"] = sha(OUT / "frozen_tasks.json")
    manifest["runner_sha256"] = sha(Path(__file__))
    manifest["source_file_hashes"] = {p: sha(ROOT / p) for p in SOURCE_FILES}
    import subprocess
    manifest["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest["expected_service_runs"] = len(tasks)
    manifest["expected_api_calls_without_retry"] = 24 * 5 + 8 * 5 + 12 * 5
    dump(manifest_path, manifest)


def tokens(text: str) -> list[str]:
    return re.findall(r"[一-龯ぁ-んァ-ンa-zA-Z0-9]+", text.lower()) + [
        text[i:i+2] for i in range(len(text)-1) if not text[i].isspace() and not text[i+1].isspace()
    ]


def bm25(question: str, corpus: list[dict], limit: int = 3) -> list[tuple[dict, float]]:
    from collections import Counter
    docs = [Counter(tokens(d["document_name"] + d["heading"] + d["content"])) for d in corpus]
    q = set(tokens(question))
    avg = sum(sum(c.values()) for c in docs) / len(docs)
    scored = []
    for row, counts in zip(corpus, docs):
        length = sum(counts.values())
        score = 0.0
        for term in q:
            df = sum(1 for other in docs if term in other)
            if df == 0:
                continue
            idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
            tf = counts[term]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
        scored.append((row, score))
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]["id"]))[:limit]


class FixedIndex:
    def __init__(self, hits):
        self.hits = hits

    def search(self, _vector, limit):
        return self.hits[:limit]


class Recorder:
    def __init__(self):
        self.events = []

    def start_request(self, question):
        self.events.append({"type": "request", "question": question})
        return uuid4()

    def record_retrieval(self, request_id, hits):
        self.events.append({"type": "retrieval", "element_ids": [str(h.element.id) for h in hits]})

    def record_generation_attempt(self, request_id, **kwargs):
        self.events.append({"type": "generation", **kwargs})
        return uuid4()

    def record_classification_attempt(self, request_id, **kwargs):
        self.events.append({"type": "classification", **kwargs})
        return uuid4()

    def record_answer_result(self, request_id, **kwargs):
        self.events.append({"type": "answer", **kwargs})
        return uuid4()


def retry_seconds(message: str) -> float:
    patterns = [r"retryDelay['\"=: ]+([0-9]+(?:\.[0-9]+)?)s", r"retry in ([0-9]+(?:\.[0-9]+)?)s", r"seconds[:= ]+([0-9]+(?:\.[0-9]+)?)"]
    for pattern in patterns:
        match = re.search(pattern, message, re.I)
        if match:
            return float(match.group(1)) + 2
    return 10.0


class Budget:
    def __init__(self, manifest, file, client):
        self.m = manifest
        self.file = file
        self.client = client
        self.start = time.monotonic()
        self.last_api_at = None
        self.attempts = 0
        self.spent = 0.0
        self.task = None
        self.step = None

    def wait_and_check(self, reserve=0.01):
        if self.attempts >= self.m["max_api_attempts"] or self.spent + reserve > self.m["max_estimated_usd"]:
            raise RuntimeError("GLOBAL_BUDGET_REACHED")
        elapsed = time.monotonic() - self.start
        if elapsed >= self.m["max_wall_seconds"]:
            raise RuntimeError("WALL_CLOCK_REACHED")
        if self.last_api_at is not None:
            time.sleep(max(0, self.m["api_min_interval_seconds"] - (time.monotonic() - self.last_api_at)))

    def call(self, prompt: str, schema: dict, phase: str):
        from google.genai import types as gt
        from src.llm_provider import StructuredLLMResult, _gemini_compatible_schema
        for retry in range(3):
            self.wait_and_check()
            self.attempts += 1
            self.last_api_at = time.monotonic()
            begin = time.monotonic()
            rec = {"task": self.task, "phase": phase, "retry": retry,
                   "api_attempt": self.attempts, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                   "prompt": prompt, "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
                   "model": self.m["model_requested"], "started_at_utc": datetime.now(timezone.utc).isoformat()}
            try:
                response = self.client.models.generate_content(
                    model=self.m["model_requested"], contents=prompt,
                    config=gt.GenerateContentConfig(
                        temperature=self.m["temperature"], seed=self.m["seed"],
                        max_output_tokens=self.m["max_output_tokens"],
                        response_mime_type="application/json",
                        response_json_schema=_gemini_compatible_schema(schema),
                    ),
                )
                rec["raw_text"] = response.text
                rec["model_version"] = response.model_version
                rec["usage"] = response.usage_metadata.model_dump() if response.usage_metadata else {}
                inp = rec["usage"].get("prompt_token_count") or 0
                out = (rec["usage"].get("candidates_token_count") or 0) + (rec["usage"].get("thoughts_token_count") or 0)
                rec["estimated_usd"] = (inp * self.m["price_assumption_usd_per_million"]["input"] + out * self.m["price_assumption_usd_per_million"]["output"]) / 1_000_000
                self.spent += rec["estimated_usd"]
                data = json.loads(response.text)
                rec["parsed_data"] = data
                result = StructuredLLMResult("gemini", self.m["model_requested"], data,
                                             inp, out, inp + out, str(getattr(response, "response_id", "") or ""))
            except Exception as exc:
                rec["error_type"] = type(exc).__name__
                rec["error"] = str(exc)[:3000]
                result = None
            rec["latency_seconds"] = round(time.monotonic() - begin, 3)
            rec["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            self.file.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self.file.flush()
            if result is not None:
                return result
            err = rec["error"].lower()
            retryable = ("429" in err or "resource_exhausted" in err or "503" in err
                         or "unavailable" in err or "timeout" in err or "deadline_exceeded" in err)
            if not retryable or retry == 2:
                raise RuntimeError(rec["error"])
            pause = retry_seconds(rec["error"])
            if time.monotonic() - self.start + pause >= self.m["max_wall_seconds"]:
                raise RuntimeError("WALL_CLOCK_REACHED_AFTER_RETRYINFO")
            time.sleep(pause)
        raise AssertionError


class Provider:
    provider_name = "gemini"

    def __init__(self, budget: Budget, phase: str):
        self.budget = budget
        self.phase = phase
        self.model = budget.m["model_requested"]

    def generate_structured(self, prompt: str, schema: dict):
        return self.budget.call(prompt, schema, self.phase)


def hits_for(row, corpus, mode):
    from src.contracts import IndexableElement, SearchHit
    if mode == "oracle":
        wanted = row["oracle_evidence_ids"]
        selected = [(next(d for d in corpus if d["id"] == key), 1.0 - i*0.01) for i, key in enumerate(wanted)]
    else:
        selected = bm25(row["question"], corpus)
    return [SearchHit(IndexableElement(id=UUID(d["element_id"]), document_id=UUID(d["document_id"]),
            version_id=UUID(d["version_id"]), document_name=d["document_name"], heading=d["heading"],
            content=d["content"], metadata={"source": "frozen-synthetic-corpus"}),
            score, i) for i, (d, score) in enumerate(selected, 1)]


def run():
    import config
    from google import genai
    from google.genai import types as gt
    from src.query_service import answer_question, load_schema
    from src.query_service_v2 import answer_question_v2
    if not config.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY unavailable")
    m = json.loads((OUT / "manifest.json").read_text())
    assert m["source_file_hashes"] and sha(OUT / "frozen_tasks.json") == m["tasks_sha256"]
    assert sha(OUT / "corpus.json") == m["corpus_sha256"] and sha(OUT / "challenge.json") == m["challenge_sha256"]
    for p, expected in m["source_file_hashes"].items():
        assert sha(ROOT / p) == expected, f"Source changed: {p}"
    tasks = json.loads((OUT / "frozen_tasks.json").read_text())
    rows = {r["id"]: r for r in json.loads((OUT / "challenge.json").read_text())}
    corpus = json.loads((OUT / "corpus.json").read_text())
    client = genai.Client(api_key=config.GOOGLE_API_KEY,
        http_options=gt.HttpOptions(timeout=int(m["http_timeout_seconds"] * 1000),
                                    retry_options=gt.HttpRetryOptions(attempts=1)))
    with (OUT / "api_attempts.jsonl").open("x") as api_file, (OUT / "service_records.jsonl").open("x") as service_file:
        budget = Budget(m, api_file, client)
        for i, task in enumerate(tasks):
            row = rows[task["row_id"]]
            hits = hits_for(row, corpus, task["evidence_mode"])
            logger = Recorder()
            budget.task = task
            start = time.monotonic()
            rec = {"index": i, **task, "question": row["question"],
                   "retrieved_ids": [str(h.element.id) for h in hits],
                   "retrieved_doc_keys": [next(d["id"] for d in corpus if d["element_id"] == str(h.element.id)) for h in hits]}
            try:
                if task["arm"] == "v1":
                    result = answer_question(row["question"], embed_query=lambda _: [0.0],
                        vector_index=FixedIndex(hits), generator=Provider(budget, "v1_generation"),
                        classifier=Provider(budget, "v1_classification"), event_logger=logger,
                        answer_schema=load_schema(ROOT / "design/schemas/answer-output-v1.schema.json"),
                        classification_schema=load_schema(ROOT / "design/schemas/classification-output-v1.schema.json"),
                        top_k=len(hits))
                else:
                    result = answer_question_v2(row["question"], embed_query=lambda _: [0.0],
                        vector_index=FixedIndex(hits), question_contract_provider=Provider(budget, "v2_question_contract"),
                        generator=Provider(budget, "v2_generation"), classifier=Provider(budget, "v2_classification"),
                        event_logger=logger,
                        question_contract_schema=load_schema(ROOT / "design/schemas/question-contract-v1.schema.json"),
                        answer_schema=load_schema(ROOT / "design/schemas/answer-output-v3-candidate.schema.json"),
                        classification_schema=load_schema(ROOT / "design/schemas/classification-output-v2-candidate.schema.json"),
                        top_k=len(hits))
                rec["result"] = result
                rec["status"] = result["answer_status"]
            except Exception as exc:
                rec["status"] = "SERVICE_ERROR"
                rec["error_type"] = type(exc).__name__
                rec["error"] = str(exc)[:3000]
            rec["events"] = logger.events
            rec["latency_seconds"] = round(time.monotonic() - start, 3)
            rec["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            service_file.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            service_file.flush()
            if (i + 1) % 8 == 0:
                print(f"{i+1}/{len(tasks)} services, {budget.attempts} attempts, estimated USD {budget.spent:.4f}", flush=True)
            if "GLOBAL_BUDGET_REACHED" in rec.get("error", "") or "WALL_CLOCK_REACHED" in rec.get("error", ""):
                print("Budget stop", flush=True)
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "run"])
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    globals()[args.mode]()
