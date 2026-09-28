"""Compare one version-conflict prompt change on fixed retrieved evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, TOP_K
from eval.compare_contextual_heading import load_baseline_query_vectors
from eval.evaluate_retrieved_text_regression import (
    DEFAULT_DOCUMENT_CACHE,
    DEFAULT_QUERY_CACHE,
    prepare_text_corpus,
)
from eval.evaluate_visual_answers import token_cost_usd
from src.answering import derive_label, parse_classification_output
from src.llm_provider import GeminiProvider
from src.query_service import (
    CLASSIFICATION_PROMPT_VERSION,
    _evidence_payload,
    build_classification_prompt_v1_from_payload,
    load_schema,
)


DEFAULT_RECORDS = (
    BASE_DIR
    / "eval/results/retrieved_text_regression_e24d7d4_v2/evaluation/records.jsonl"
)
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
CANDIDATE_PROMPT_VERSION = "answer-classification-version-conflict-v1"
RESERVE_USD_PER_CALL = 0.002

TARGET_IDS = {
    "Q121",
    "Q196",
    "Q201",
    "Q231",
    "Q281",
    "Q286",
    "Q416",
}
TRUE_VERSION_CONFLICT_IDS = {"Q176"}
OTHER_JUDGMENT_CONTROL_IDS = {
    "Q166",
    "Q171",
    "Q206",
    "Q211",
    "Q306",
    "Q311",
    "Q396",
}
INSUFFICIENT_CONTROL_IDS = {"Q451", "Q456"}
SELECTED_IDS = (
    TARGET_IDS
    | TRUE_VERSION_CONFLICT_IDS
    | OTHER_JUDGMENT_CONTROL_IDS
    | INSUFFICIENT_CONTROL_IDS
)


def build_version_conflict_prompt(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    payload = json.dumps(
        {
            "question": question,
            "retrieved_evidence": evidence,
            "generated_answer": answer_data,
        },
        ensure_ascii=False,
    )
    return (
        "classification-output-v1に従い、ラベルではなく5つの判定要因をJSONで返してください。"
        "corpus全体に答えが存在するかは判定しないでください。\n"
        "version_conflictだけは次の境界で判定してください。他の4要因の判定規則は変更しません。\n"
        "- version_conflict=trueは、文書版の違いが質問の結論に関係し、質問の基準日、"
        "根拠の施行日・適用期間、明示された優先規則を使っても適用版を一意に決められない"
        "場合だけです。\n"
        "- 旧版と新版の両方が取得された、または改正前後の記述が存在するという事実だけでは"
        "version_conflict=trueにしません。適用版を解決できればfalseです。\n"
        "- 例: 質問が2025年10月を明示し、根拠が2025年10月1日から新版を適用すると定めるなら"
        "version_conflict=falseです。\n"
        "- 例: 質問に基準日がなく、適用可能な旧版と新版の結論が異なり、優先規則もなければ"
        "version_conflict=trueです。\n"
        f"判定対象: {payload}"
    )


PROMPTS: dict[str, tuple[str, Callable[[str, list[dict], dict], str]]] = {
    "baseline": (
        CLASSIFICATION_PROMPT_VERSION,
        build_classification_prompt_v1_from_payload,
    ),
    "candidate": (CANDIDATE_PROMPT_VERSION, build_version_conflict_prompt),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    records = {row["question_id"]: row for row in rows}
    if len(records) != len(rows):
        raise ValueError("question_idが重複しています")
    return records


def select_cases(records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    missing = SELECTED_IDS - set(records)
    if missing:
        raise ValueError(f"比較対象がrecordsにありません: {sorted(missing)}")
    cases = []
    for question_id in sorted(SELECTED_IDS):
        record = records[question_id]
        if question_id in TARGET_IDS:
            role = "target_resolved_version"
        elif question_id in TRUE_VERSION_CONFLICT_IDS:
            role = "control_true_version_conflict"
        elif question_id in OTHER_JUDGMENT_CONTROL_IDS:
            role = "control_other_judgment"
        else:
            role = "control_insufficient"
        cases.append({**record, "role": role})
    return cases


def _answer_payload(case: dict[str, Any]) -> dict[str, Any]:
    claims = []
    for claim in case["claims"]:
        claims.append(
            {
                "claim_id": claim["claim_id"],
                "ordinal": claim["ordinal"],
                "text": claim["text"],
                "evidence_element_ids": claim["evidence_element_ids"],
                "evidence_kind": claim.get("evidence_kind", "text"),
            }
        )
    return {
        "schema_version": "1.0",
        "claims": claims,
        "missing_conditions": case["missing_conditions"],
    }


def summarize(records: list[dict[str, Any]], case_count: int) -> dict[str, Any]:
    by_prompt = {}
    for prompt_name in PROMPTS:
        selected = [record for record in records if record["prompt"] == prompt_name]
        completed = [record for record in selected if record["error"] is None]
        by_prompt[prompt_name] = {
            "attempted": len(selected),
            "completed": len(completed),
            "correct": sum(record["correct"] for record in completed),
            "target_correct": sum(
                record["correct"]
                for record in completed
                if record["role"] == "target_resolved_version"
            ),
            "control_correct": sum(
                record["correct"]
                for record in completed
                if record["role"] != "target_resolved_version"
            ),
        }
    baseline = {
        record["question_id"]: record
        for record in records
        if record["prompt"] == "baseline" and record["error"] is None
    }
    candidate = {
        record["question_id"]: record
        for record in records
        if record["prompt"] == "candidate" and record["error"] is None
    }
    improvements = sorted(
        question_id
        for question_id in baseline.keys() & candidate.keys()
        if not baseline[question_id]["correct"] and candidate[question_id]["correct"]
    )
    regressions = sorted(
        question_id
        for question_id in baseline.keys() & candidate.keys()
        if baseline[question_id]["correct"] and not candidate[question_id]["correct"]
    )
    target_improvements = [item for item in improvements if item in TARGET_IDS]
    control_regressions = [item for item in regressions if item not in TARGET_IDS]
    return {
        "case_count": case_count,
        "logical_external_call_count": len(records),
        "error_count": sum(record["error"] is not None for record in records),
        "stop_reason": (
            "PROVIDER_ERROR_FAIL_FAST"
            if any(record["error"] is not None for record in records)
            else "COMPLETED"
        ),
        "by_prompt": by_prompt,
        "improvements": improvements,
        "regressions": regressions,
        "gate": {
            "target_improvement_count": len(target_improvements),
            "control_regression_count": len(control_regressions),
            "passed": bool(target_improvements) and not control_regressions,
        },
    }


def run_comparison(
    *,
    records_path: Path,
    query_cache: Path,
    document_cache: Path,
    output_dir: Path,
    max_logical_external_calls: int,
    max_cost_usd: float,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"結果は上書きしません: {output_dir}")
    cases = select_cases(_read_jsonl(records_path))
    expected_calls = len(cases) * len(PROMPTS)
    if max_logical_external_calls != expected_calls:
        raise ValueError(f"logical external call上限は{expected_calls}で固定します")
    if max_cost_usd < expected_calls * RESERVE_USD_PER_CALL:
        raise ValueError("cost上限が全callの予約額を下回っています")

    index = prepare_text_corpus(document_cache)
    query_vectors = load_baseline_query_vectors(query_cache, cases)
    evidence_by_id = {}
    for case in cases:
        hits = index.search(query_vectors[case["question"]], TOP_K)
        expected_ids = [item["element_id"] for item in case["retrieved"]]
        actual_ids = [str(hit.element.id) for hit in hits]
        if actual_ids != expected_ids:
            raise ValueError(f"保存済み検索結果を再現できません: {case['question_id']}")
        evidence_by_id[case["question_id"]] = _evidence_payload(hits)

    output_dir.mkdir(parents=True)
    records_output = output_dir / "records.jsonl"
    manifest = {
        "experiment": "version-conflict-prompt-v1",
        "records_path": str(records_path.relative_to(BASE_DIR)),
        "records_sha256": _sha256(records_path),
        "query_cache_sha256": _sha256(query_cache),
        "document_cache_sha256": _sha256(document_cache),
        "model": CLASSIFIER_MODEL_NAME,
        "case_count": len(cases),
        "target_count": len(TARGET_IDS),
        "control_count": len(cases) - len(TARGET_IDS),
        "max_logical_external_calls": max_logical_external_calls,
        "max_cost_usd": max_cost_usd,
        "retry_count": 0,
        "sealed_holdout_accessed": False,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )

    provider = GeminiProvider(CLASSIFIER_MODEL_NAME)
    schema = load_schema(CLASSIFICATION_SCHEMA)
    results = []
    input_tokens = 0
    output_tokens = 0
    for case in cases:
        answer_data = _answer_payload(case)
        for prompt_name, (prompt_version, builder) in PROMPTS.items():
            if (
                token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_CALL
                > max_cost_usd
            ):
                raise RuntimeError("cost上限へ達する前に比較を完了できません")
            error = None
            response_data = None
            predicted_label = None
            case_input = 0
            case_output = 0
            try:
                response = provider.generate_structured(
                    builder(
                        case["question"],
                        evidence_by_id[case["question_id"]],
                        answer_data,
                    ),
                    schema,
                )
                response_data = response.data
                case_input = response.input_tokens
                case_output = response.output_tokens
                predicted_label = derive_label(
                    parse_classification_output(response_data).factors
                )
            except Exception as exception:
                error = f"{type(exception).__name__}: {exception}"
            input_tokens += case_input
            output_tokens += case_output
            result = {
                "question_id": case["question_id"],
                "role": case["role"],
                "expected_label": case["expected_label"],
                "prompt": prompt_name,
                "prompt_version": prompt_version,
                "predicted_label": predicted_label,
                "correct": predicted_label == case["expected_label"],
                "response": response_data,
                "input_tokens": case_input,
                "output_tokens": case_output,
                "error": error,
            }
            results.append(result)
            with records_output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            if error:
                break
        if results[-1]["error"]:
            break

    summary = summarize(results, len(cases))
    summary.update(
        {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
            "max_cost_usd": max_cost_usd,
        }
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--query-cache", type=Path, default=DEFAULT_QUERY_CACHE)
    parser.add_argument("--document-cache", type=Path, default=DEFAULT_DOCUMENT_CACHE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    summary = run_comparison(
        records_path=args.records.resolve(),
        query_cache=args.query_cache.resolve(),
        document_cache=args.document_cache.resolve(),
        output_dir=args.output_dir.resolve(),
        max_logical_external_calls=args.max_logical_external_calls,
        max_cost_usd=args.max_cost_usd,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
