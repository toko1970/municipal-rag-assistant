"""Evaluate a local binary NLI classifier on the fixed 36-case benchmark."""

from __future__ import annotations

import argparse
import json
import resource
import time
from collections import Counter
from pathlib import Path
from typing import Any

from eval.run_local_nli_classifier_pilot import (
    FACTOR_HYPOTHESES,
    build_premise,
    portable_path,
)
from eval.validate_classifier_model_benchmark import derive_label


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def binary_metrics(gold: list[bool], predicted: list[bool]) -> dict[str, Any]:
    true_positive = sum(g and p for g, p in zip(gold, predicted, strict=True))
    false_positive = sum(not g and p for g, p in zip(gold, predicted, strict=True))
    false_negative = sum(g and not p for g, p in zip(gold, predicted, strict=True))
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def multiclass_f1(
    expected: list[str], predicted: list[str], labels: tuple[str, ...]
) -> dict[str, Any]:
    by_label = {}
    for label in labels:
        gold = [value == label for value in expected]
        guesses = [value == label for value in predicted]
        by_label[label] = binary_metrics(gold, guesses)
    return {
        "by_label": by_label,
        "macro_f1": sum(item["f1"] for item in by_label.values()) / len(labels),
    }


def summarize(cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    indexed = {(r["case_id"], r["factor"]): r for r in records}
    case_results = []
    factor_metrics = {}
    for factor in FACTOR_HYPOTHESES:
        gold = [case["expected_factors"][factor] for case in cases]
        predicted = [indexed[(case["case_id"], factor)]["predicted"] for case in cases]
        factor_metrics[factor] = binary_metrics(gold, predicted)

    for case in cases:
        factors = {
            factor: indexed[(case["case_id"], factor)]["predicted"]
            for factor in FACTOR_HYPOTHESES
        }
        predicted_label = derive_label(factors)
        case_results.append(
            {
                "case_id": case["case_id"],
                "modality": case["modality"],
                "expected_factors": case["expected_factors"],
                "predicted_factors": factors,
                "factor_exact_match": factors == case["expected_factors"],
                "expected_label": case["expected_label"],
                "predicted_label": predicted_label,
                "label_correct": predicted_label == case["expected_label"],
                "critical_error": (
                    case["expected_label"] in {"判断要", "文書不足"}
                    and predicted_label == "根拠十分"
                ),
            }
        )

    expected_labels = [item["expected_label"] for item in case_results]
    predicted_labels = [item["predicted_label"] for item in case_results]
    return {
        "factor_metrics": factor_metrics,
        "factor_exact_match_count": sum(item["factor_exact_match"] for item in case_results),
        "label_correct_count": sum(item["label_correct"] for item in case_results),
        "label_accuracy": sum(item["label_correct"] for item in case_results) / len(case_results),
        "label_counts": dict(Counter(predicted_labels)),
        "label_metrics": multiclass_f1(
            expected_labels, predicted_labels, ("根拠十分", "判断要", "文書不足")
        ),
        "critical_error_count": sum(item["critical_error"] for item in case_results),
        "case_results": case_results,
    }


def run(
    *,
    dataset_path: Path,
    audit_path: Path,
    model_path: Path,
    model_id: str,
    output_path: Path,
    max_pairs: int,
) -> dict[str, Any]:
    # Heavy local-model dependencies are optional evaluation dependencies.
    # Keep metric helpers importable in CI, which intentionally installs only
    # the normal development requirements.
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if output_path.exists():
        raise FileExistsError(f"結果は上書きしません: {output_path}")
    dataset = load_json(dataset_path)
    audit = load_json(audit_path)
    expected_pairs = len(dataset["cases"]) * len(FACTOR_HYPOTHESES)
    if max_pairs != expected_pairs:
        raise ValueError(f"max-pairsは{expected_pairs}で固定します")
    if audit["status"] != "READY_FOR_LOCAL_INFERENCE":
        raise ValueError("token auditがlocal inferenceを許可していません")
    if audit["model"] != model_id:
        raise ValueError("token auditとmodel IDが一致しません")
    if audit["audit"]["pair_count"] != expected_pairs:
        raise ValueError("token auditのpair数がbenchmarkと一致しません")

    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_path, local_files_only=True
    )
    config_max = model.config.max_position_embeddings
    tokenizer.model_max_length = config_max - 2
    if set(model.config.label2id) != {"entailment", "not_entailment"}:
        raise ValueError(f"binary NLI label契約が不正です: {model.config.label2id}")
    entailment_id = model.config.label2id["entailment"]
    not_entailment_id = model.config.label2id["not_entailment"]
    load_seconds = time.perf_counter() - started

    records = []
    inference_started = time.perf_counter()
    for case in dataset["cases"]:
        premise = build_premise(case)
        for factor, hypothesis in FACTOR_HYPOTHESES.items():
            encoded = tokenizer(
                premise,
                hypothesis,
                return_tensors="pt",
                truncation=False,
            )
            token_count = encoded["input_ids"].shape[1]
            if token_count > tokenizer.model_max_length:
                raise ValueError(
                    f"token audit後に上限超過を検出しました: {case['case_id']} / {factor}"
                )
            pair_started = time.perf_counter()
            with torch.inference_mode():
                logits = model(**encoded).logits[0].float()
            pair_seconds = time.perf_counter() - pair_started
            probabilities = torch.softmax(logits, dim=-1)
            predicted = bool(
                probabilities[entailment_id] > probabilities[not_entailment_id]
            )
            records.append(
                {
                    "case_id": case["case_id"],
                    "factor": factor,
                    "expected": case["expected_factors"][factor],
                    "predicted": predicted,
                    "correct": predicted == case["expected_factors"][factor],
                    "token_count": token_count,
                    "seconds": pair_seconds,
                    "logits": logits.tolist(),
                    "probabilities": probabilities.tolist(),
                }
            )
            if len(records) % 10 == 0:
                print(f"completed_pairs={len(records)}/{expected_pairs}", flush=True)

    inference_seconds = time.perf_counter() - inference_started
    result = {
        "schema_version": "1.0",
        "status": "SUCCESS",
        "model": model_id,
        "model_revision": model_path.name,
        "dataset": portable_path(dataset_path),
        "audit": portable_path(audit_path),
        "pair_count": len(records),
        "load_seconds": load_seconds,
        "inference_seconds": inference_seconds,
        "mean_pair_seconds": inference_seconds / len(records),
        "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024),
        "model_config_max_position_embeddings": config_max,
        "decision_rule": "entailment_probability > not_entailment_probability",
        "threshold_tuned_on_benchmark": False,
        "external_api_calls": 0,
        "estimated_external_cost_usd": 0,
        "sealed_holdout_used": False,
        "summary": summarize(dataset["cases"], records),
        "records": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=root / "eval/classifier_model_benchmark_v1.json",
    )
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pairs", type=int, required=True)
    args = parser.parse_args()
    result = run(
        dataset_path=args.dataset.resolve(),
        audit_path=args.audit.resolve(),
        model_path=args.model_path.resolve(),
        model_id=args.model_id,
        output_path=args.output.resolve(),
        max_pairs=args.max_pairs,
    )
    summary = result["summary"]
    print(
        f"status=SUCCESS labels={summary['label_correct_count']}/{len(summary['case_results'])} "
        f"macro_f1={summary['label_metrics']['macro_f1']:.4f} "
        f"critical={summary['critical_error_count']}"
    )


if __name__ == "__main__":
    main()
