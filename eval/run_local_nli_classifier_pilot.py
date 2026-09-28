"""Audit a fixed classifier benchmark for a local NLI model.

The audit is intentionally separate from inference.  It records the exact
premise/hypothesis contract and refuses to silently truncate overlong pairs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from transformers import AutoTokenizer


FACTOR_HYPOTHESES = {
    "retrieval_sufficient": "取得根拠には、質問へ答えるために必要な情報が揃っている。",
    "answer_fully_supported": "回答の重要な主張は、取得根拠によってすべて支持されている。",
    "requires_case_facts": "質問が求める結論には、まだ示されていない個別事実が必要である。",
    "requires_policy_judgment": "必要事実が揃っても、制度所管部署の判断または複数解釈が残る。",
    "version_conflict": "質問へ適用する文書版を一意に決められない。",
}


class PairTokenizer(Protocol):
    model_max_length: int

    def __call__(
        self,
        text: str,
        text_pair: str,
        *,
        add_special_tokens: bool,
        truncation: bool,
    ) -> dict[str, Any]: ...


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path.resolve())


def build_premise(case: dict[str, Any]) -> str:
    evidence = "\n".join(
        f"- [{item['element_id']}] {item['content']}" for item in case["evidence"]
    )
    claims = "\n".join(
        f"- [{claim['claim_id']}] {claim['text']}"
        for claim in case["generated_answer"]["claims"]
    )
    missing = "\n".join(
        f"- {condition}"
        for condition in case["generated_answer"]["missing_conditions"]
    )
    return (
        f"質問:\n{case['question']}\n\n"
        f"取得根拠:\n{evidence or '- なし'}\n\n"
        f"生成済みの主張:\n{claims or '- なし'}\n\n"
        f"不足条件:\n{missing or '- なし'}"
    )


def count_pair_tokens(
    tokenizer: PairTokenizer, premise: str, hypothesis: str
) -> int:
    encoded = tokenizer(
        premise,
        hypothesis,
        add_special_tokens=True,
        truncation=False,
    )
    input_ids = encoded["input_ids"]
    if input_ids and isinstance(input_ids[0], list):
        input_ids = input_ids[0]
    return len(input_ids)


def audit_token_lengths(
    dataset: dict[str, Any], tokenizer: PairTokenizer, *, max_tokens: int
) -> dict[str, Any]:
    records = []
    for case in dataset["cases"]:
        premise = build_premise(case)
        for factor, hypothesis in FACTOR_HYPOTHESES.items():
            token_count = count_pair_tokens(tokenizer, premise, hypothesis)
            records.append(
                {
                    "case_id": case["case_id"],
                    "factor": factor,
                    "token_count": token_count,
                    "exceeds_limit": token_count > max_tokens,
                }
            )

    over_limit = [record for record in records if record["exceeds_limit"]]
    return {
        "pair_count": len(records),
        "case_count": len(dataset["cases"]),
        "max_tokens": max_tokens,
        "maximum_observed_tokens": max(
            (record["token_count"] for record in records), default=0
        ),
        "over_limit_pair_count": len(over_limit),
        "over_limit_case_count": len({record["case_id"] for record in over_limit}),
        "over_limit_pairs": over_limit,
        "records": records,
    }


def run_audit(
    *,
    dataset_path: Path,
    model_path: Path,
    model_id: str,
    output_dir: Path,
    max_tokens: int,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"結果は上書きしません: {output_dir}")
    dataset = load_json(dataset_path)
    if dataset.get("review_status") != "approved":
        raise ValueError("approved benchmarkだけを監査できます")

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    audit = audit_token_lengths(dataset, tokenizer, max_tokens=max_tokens)
    status = (
        "BLOCKED_BY_CONTEXT_LIMIT"
        if audit["over_limit_pair_count"]
        else "READY_FOR_LOCAL_INFERENCE"
    )
    result = {
        "schema_version": "1.0",
        "status": status,
        "dataset": portable_path(dataset_path),
        "dataset_sha256": sha256(dataset_path),
        "model": model_id,
        "model_revision": model_path.name,
        "tokenizer_class": type(tokenizer).__name__,
        "tokenizer_reported_max_length": tokenizer.model_max_length,
        "inference_executed": False,
        "external_api_calls": 0,
        "estimated_external_cost_usd": 0,
        "sealed_holdout_used": False,
        "hypotheses": FACTOR_HYPOTHESES,
        "audit": audit,
    }
    output_dir.mkdir(parents=True)
    (output_dir / "token_audit.json").write_text(
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
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "eval/results/classifier_model_mdeberta_pilot_v1",
    )
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()

    result = run_audit(
        dataset_path=args.dataset.resolve(),
        model_path=args.model_path.resolve(),
        model_id=args.model_id,
        output_dir=args.output_dir.resolve(),
        max_tokens=args.max_tokens,
    )
    audit = result["audit"]
    print(
        f"status={result['status']} pairs={audit['pair_count']} "
        f"max={audit['maximum_observed_tokens']} "
        f"over_limit={audit['over_limit_pair_count']}"
    )


if __name__ == "__main__":
    main()
