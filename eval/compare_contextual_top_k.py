"""Compare retrieval depth for the fixed contextual-heading candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.compare_contextual_heading import (
    COLLECTION_NAME,
    load_baseline_query_vectors,
)
from eval.compare_vector_backends import filter_questions
from eval.evaluate_retrieval import (
    expected_document_ids,
    expected_evidence,
    load_evaluation_questions,
)
from src.qdrant_index import QdrantVectorIndex


def metrics_for_ranking(
    retrieved_pairs: list[tuple[str, str]],
    required_ids: list[str],
    required_evidence: list[tuple[str, str]],
    k_values: list[int],
) -> dict[str, dict[str, int | float]]:
    metrics = {}
    for k in k_values:
        top_pairs = retrieved_pairs[:k]
        found_ids = {document_id for document_id, _heading in top_pairs}
        found_evidence = set(top_pairs)
        metrics[str(k)] = {
            "document_recall": (
                len(found_ids.intersection(required_ids)) / len(required_ids)
                if required_ids
                else 0.0
            ),
            "document_hit": int(bool(required_ids) and set(required_ids) <= found_ids),
            "evidence_recall": (
                len(found_evidence.intersection(required_evidence))
                / len(required_evidence)
                if required_evidence
                else 0.0
            ),
            "evidence_hit": int(
                bool(required_evidence)
                and set(required_evidence) <= found_evidence
            ),
        }
    return metrics


def smallest_complete_k(metrics: dict[str, dict], metric: str) -> int | None:
    complete = [int(k) for k, values in metrics.items() if values[metric]]
    return min(complete) if complete else None


def heading_path(metadata: dict) -> str:
    return " > ".join(
        str(metadata[key])
        for key in ("見出し1", "見出し2", "見出し3")
        if metadata.get(key)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--query-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-k", type=int, default=5)
    parser.add_argument("--max-k", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.min_k <= args.max_k:
        raise ValueError("1 <= min-k <= max-kで指定してください")

    questions = filter_questions(
        load_evaluation_questions(args.input), "formal"
    )
    vectors = load_baseline_query_vectors(args.query_cache, questions)
    index = QdrantVectorIndex(collection_name=COLLECTION_NAME)
    k_values = list(range(args.min_k, args.max_k + 1))
    records = []

    for row in questions:
        required_ids = expected_document_ids(row)
        required_sections = expected_evidence(row, required_ids)
        hits = index.search(vectors[row["question"]], limit=args.max_k)
        retrieved = [
            (
                str(hit.element.metadata.get("document_id", "")),
                heading_path(hit.element.metadata),
            )
            for hit in hits
        ]
        metrics = metrics_for_ranking(
            retrieved, required_ids, required_sections, k_values
        )
        records.append(
            {
                "question_id": row["question_id"],
                "question": row["question"],
                "retrieval_applicable": bool(required_ids),
                "expected_document_ids": required_ids,
                "expected_evidence": [list(item) for item in required_sections],
                "retrieved": [
                    {
                        "rank": rank,
                        "document_id": document_id,
                        "heading": heading,
                        "content_chars": len(hit.element.content),
                    }
                    for rank, ((document_id, heading), hit) in enumerate(
                        zip(retrieved, hits, strict=True), start=1
                    )
                ],
                "metrics": metrics,
                "smallest_document_hit_k": smallest_complete_k(
                    metrics, "document_hit"
                ),
                "smallest_evidence_hit_k": smallest_complete_k(
                    metrics, "evidence_hit"
                ),
            }
        )

    applicable = [record for record in records if record["retrieval_applicable"]]
    summary = []
    for k in k_values:
        key = str(k)
        summary.append(
            {
                "k": k,
                "document_hits": sum(
                    record["metrics"][key]["document_hit"] for record in applicable
                ),
                "evidence_hits": sum(
                    record["metrics"][key]["evidence_hit"] for record in applicable
                ),
                "applicable_questions": len(applicable),
                "mean_context_chars": sum(
                    sum(item["content_chars"] for item in record["retrieved"][:k])
                    for record in records
                )
                / len(records),
            }
        )

    output = {
        "experiment": "contextual-heading-top-k",
        "collection_name": COLLECTION_NAME,
        "questions": len(records),
        "retrieval_applicable": len(applicable),
        "k_values": k_values,
        "summary": summary,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
