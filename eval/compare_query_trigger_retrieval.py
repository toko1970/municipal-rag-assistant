"""Compare dense and decomposed retrieval on frozen paraphrase cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from config import BASE_DIR, GOOGLE_API_KEY
from eval.compare_embedding_models import load_or_create_vectors
from eval.embedding_profiles import PROFILES, GeminiOneEmbedder
from eval.evaluate_retrieved_text_regression import prepare_text_corpus
from eval.rejected_query_trigger_candidate import decompose_query, retrieve_decomposed


DEFAULT_INPUT = BASE_DIR / "eval/query_trigger_robustness_cases.json"
DEFAULT_DOCUMENT_CACHE = BASE_DIR / ".eval_cache/contextual_heading_gemini_001_documents.json"
DEFAULT_QUERY_CACHE = BASE_DIR / ".eval_cache/query_trigger_robustness_queries.json"
MAX_LOGICAL_EXTERNAL_CALLS = 1
MAX_COST_USD = 0.001
TOP_K = 8


def _evidence_key(hit) -> str:
    metadata = hit.element.metadata
    heading = " > ".join(
        str(metadata[key])
        for key in ("見出し1", "見出し2", "見出し3")
        if metadata.get(key)
    )
    return f"{metadata.get('document_id', '')}::{heading}"


def _required_groups(family: str) -> list[set[str]]:
    if family == "move_positive":
        return [
            {"DOC-002::2. 通勤手当 > 2.4 支給停止"},
            {
                "DOC-004::2. 住所変更届 > 2.1 提出が必要な場合",
                "DOC-004::2. 住所変更届 > 2.2 提出期限",
            },
        ]
    if family == "birth_positive":
        return [
            {"DOC-005::5. 扶養手当の改正 > 改正後"},
            {"DOC-005::5. 扶養手当の改正 > 経過措置"},
            {"DOC-004::3. 扶養親族変更届 > 3.2 提出期限"},
        ]
    raise ValueError(f"検索正解が未定義のfamilyです: {family}")


def _retrieval_ok(hits, groups: list[set[str]]) -> bool:
    actual = {_evidence_key(hit) for hit in hits}
    return all(actual.intersection(group) for group in groups)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_cost_usd > MAX_COST_USD:
        raise ValueError(f"費用上限はUS${MAX_COST_USD}以下にしてください")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    cases = [
        case
        for case in payload["cases"]
        if case["family"] in {"move_positive", "birth_positive"}
    ]
    subqueries = list(
        dict.fromkeys(
            query
            for case in cases
            for query in decompose_query(case["question"])
            if query != case["question"]
        )
    )
    texts = [case["question"] for case in cases] + subqueries
    profile = PROFILES["gemini-embedding-001"]
    ids = [f"query:{hashlib.sha256(text.encode()).hexdigest()}" for text in texts]
    embedder = GeminiOneEmbedder(profile, GOOGLE_API_KEY)
    vectors, _cache_hit, _elapsed = load_or_create_vectors(
        args.query_cache,
        profile=profile,
        kind="query-trigger-robustness-v1",
        ids=ids,
        texts=texts,
        embed=embedder.embed_queries,
    )
    if embedder.request_count > MAX_LOGICAL_EXTERNAL_CALLS:
        raise RuntimeError("Embeddingのlogical external call上限を超えました")
    vectors_by_text = dict(zip(texts, vectors, strict=True))
    index = prepare_text_corpus(args.document_cache)

    records = []
    for case in cases:
        question = case["question"]
        baseline = index.search(vectors_by_text[question], TOP_K)
        candidate = retrieve_decomposed(
            question,
            top_k=TOP_K,
            search=lambda query, limit: index.search(vectors_by_text[query], limit),
        )
        groups = _required_groups(case["family"])
        records.append(
            {
                "id": case["id"],
                "family": case["family"],
                "question": question,
                "baseline_ok": _retrieval_ok(baseline, groups),
                "candidate_ok": _retrieval_ok(candidate, groups),
                "baseline_evidence": [_evidence_key(hit) for hit in baseline],
                "candidate_evidence": [_evidence_key(hit) for hit in candidate],
            }
        )

    args.output_dir.mkdir(parents=True)
    (args.output_dir / "records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    baseline_success = sum(row["baseline_ok"] for row in records)
    candidate_success = sum(row["candidate_ok"] for row in records)
    regressions = [row["id"] for row in records if row["baseline_ok"] and not row["candidate_ok"]]
    improvements = [row["id"] for row in records if not row["baseline_ok"] and row["candidate_ok"]]
    summary = {
        "case_count": len(records),
        "baseline_success": baseline_success,
        "candidate_success": candidate_success,
        "improved_ids": improvements,
        "regressed_ids": regressions,
        "gate_passed": candidate_success > baseline_success and not regressions,
        "embedding_logical_external_calls": embedder.request_count,
        "max_logical_external_calls": MAX_LOGICAL_EXTERNAL_CALLS,
        "max_cost_usd": args.max_cost_usd,
        "retry_count": 0,
        "sealed_holdout_accessed": False,
    }
    manifest = {
        "experiment": "query-trigger-retrieval-comparison-v1",
        "dataset_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "document_cache_sha256": hashlib.sha256(args.document_cache.read_bytes()).hexdigest(),
        "embedding_profile": profile.manifest(),
        "top_k": TOP_K,
        **{key: summary[key] for key in ("max_logical_external_calls", "max_cost_usd", "retry_count", "sealed_holdout_accessed")},
    }
    for name, value in (("summary.json", summary), ("run_manifest.json", manifest)):
        (args.output_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
