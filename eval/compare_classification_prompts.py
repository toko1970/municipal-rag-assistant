"""Compare classifier prompts on fixed oracle-evidence development cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from config import BASE_DIR, CLASSIFIER_MODEL_NAME
from eval.evaluate_visual_answers import token_cost_usd
from src.answering import derive_label, parse_classification_output
from src.llm_provider import GeminiProvider
from src.query_service import (
    CLASSIFICATION_PROMPT_VERSION,
    build_classification_prompt_v1_from_payload,
    load_schema,
)


DEFAULT_CASES = BASE_DIR / "eval/classification_prompt_development_cases.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
RESERVE_USD_PER_CALL = 0.002
CANDIDATE_CLASSIFICATION_PROMPT_VERSION = "answer-classification-v2"
EXAMPLE_CLASSIFICATION_PROMPT_VERSION = "answer-classification-v3"


def _classification_payload(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    return json.dumps(
        {
            "question": question,
            "retrieved_evidence": evidence,
            "generated_answer": answer_data,
        },
        ensure_ascii=False,
    )


def build_classification_prompt_v2_from_payload(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    payload = _classification_payload(question, evidence, answer_data)
    return (
        "classification-output-v1に従い、ラベルではなく5つの判定要因をJSONで返してください。"
        "corpus全体に答えが存在するかは判定しないでください。\n"
        "判定規則:\n"
        "- 質問へ答える具体的なclaimが取得根拠で支持され、結論を変える不足条件がなければ、"
        "retrieval_sufficientとanswer_fully_supportedをtrueにします。\n"
        "- requires_case_factsは、結論を決める具体的な個別事実が質問にも根拠にもなく、"
        "generated_answer.missing_conditionsにその事実が明記されている場合だけtrueにします。"
        "一般的な『個別事情の確認』を推測してtrueにしてはいけません。\n"
        "- requires_policy_judgmentは、根拠が複数の正当な解釈または明示的な裁量を残す場合だけ"
        "trueにします。以上・以下・未満・超、またはflowの明示的な分岐を適用するだけなら"
        "falseです。\n"
        "- version_conflictは、質問へ適用可能な文書版が実際に競合し、根拠だけでは選べない場合"
        "だけtrueです。\n"
        "- 取得根拠から結論を確認できない場合はretrieval_sufficientをfalseにします。\n"
        f"判定対象: {payload}"
    )


def build_classification_prompt_v3_from_payload(
    question: str, evidence: list[dict], answer_data: dict
) -> str:
    payload = _classification_payload(question, evidence, answer_data)
    return (
        "classification-output-v1に従い、ラベルではなく5つの判定要因をJSONで返してください。"
        "corpus全体に答えが存在するかは判定しないでください。\n"
        "判定順序:\n"
        "1. 取得根拠が質問へ答えられなければretrieval_sufficient=falseとし、"
        "requires_case_factsとrequires_policy_judgmentはfalseにします。\n"
        "2. 質問に具体的な数値・状態があり、根拠の以上・以下・未満・超またはflow分岐を"
        "そのまま適用して結論が一つに決まる場合、requires_case_facts=false、"
        "requires_policy_judgment=falseです。現実には別事情があり得る、という一般論を"
        "追加してはいけません。\n"
        "3. 根拠が要求する具体的な事実を質問が示しておらず、その値で結論が変わる場合だけ"
        "requires_case_facts=trueです。generated_answerが確認必要と述べる場合も、その確認が"
        "結論を変える具体的事実か確認します。\n"
        "4. 根拠が明示的な裁量または複数の正当な解釈を残す場合だけ"
        "requires_policy_judgment=trueです。\n"
        "例A: 質問『45分で講習修了済みなら認定か』、根拠『45分以上かつ講習修了なら認定』"
        "ならcase facts=false、policy judgment=falseです。\n"
        "例B: 質問『この職員は認定か』、根拠『45分以上かつ講習修了なら認定』で講習状況が"
        "不明ならcase facts=trueです。\n"
        "例C: 質問と無関係な根拠しかなければretrieval sufficient=false、case facts=falseです。\n"
        f"判定対象: {payload}"
    )


PROMPTS: dict[str, tuple[str, Callable[[str, list[dict], dict], str]]] = {
    "baseline": (
        CLASSIFICATION_PROMPT_VERSION,
        build_classification_prompt_v1_from_payload,
    ),
    "candidate": (
        CANDIDATE_CLASSIFICATION_PROMPT_VERSION,
        build_classification_prompt_v2_from_payload,
    ),
    "candidate_v3": (
        EXAMPLE_CLASSIFICATION_PROMPT_VERSION,
        build_classification_prompt_v3_from_payload,
    ),
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_cases(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    cases = dataset.get("cases")
    if not isinstance(cases, list) or len(cases) != dataset.get("case_count"):
        raise ValueError("case_countとcases件数が一致しません")
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case IDが重複しています")
    label_counts = {
        label: sum(case.get("expected_label") == label for case in cases)
        for label in dataset["expected_counts"]
    }
    modality_counts = {
        modality: sum(case.get("modality") == modality for case in cases)
        for modality in dataset["modality_counts"]
    }
    if label_counts != dataset["expected_counts"]:
        raise ValueError("期待ラベル件数がdataset定義と一致しません")
    if modality_counts != dataset["modality_counts"]:
        raise ValueError("modality件数がdataset定義と一致しません")
    return cases


def summarize(records: list[dict[str, Any]], case_count: int) -> dict[str, Any]:
    by_prompt = {}
    for prompt_name in PROMPTS:
        selected = [record for record in records if record["prompt"] == prompt_name]
        completed = [record for record in selected if record["error"] is None]
        by_prompt[prompt_name] = {
            "attempted": len(selected),
            "completed": len(completed),
            "correct": sum(record["correct"] for record in completed),
            "accuracy": (
                sum(record["correct"] for record in completed) / len(completed)
                if completed
                else None
            ),
            "text_correct": sum(
                record["correct"]
                for record in completed
                if record["modality"] == "text"
            ),
            "visual_correct": sum(
                record["correct"]
                for record in completed
                if record["modality"] == "visual"
            ),
        }
    return {
        "case_count": case_count,
        "logical_external_call_count": len(records),
        "error_count": sum(record["error"] is not None for record in records),
        "by_prompt": by_prompt,
    }


def run_comparison(
    *,
    dataset_path: Path,
    output_path: Path,
    max_logical_external_calls: int,
    max_cost_usd: float,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"結果は上書きしません: {output_path}")
    dataset = _load_json(dataset_path)
    cases = validate_cases(dataset)
    expected_calls = len(cases) * len(PROMPTS)
    if max_logical_external_calls != expected_calls:
        raise ValueError(f"logical external call上限は{expected_calls}で固定します")
    if max_cost_usd < expected_calls * RESERVE_USD_PER_CALL:
        raise ValueError("cost上限が全callの予約額を下回っています")

    provider = GeminiProvider(CLASSIFIER_MODEL_NAME)
    schema = load_schema(CLASSIFICATION_SCHEMA)
    records = []
    input_tokens = 0
    output_tokens = 0
    for case in cases:
        for prompt_name, (prompt_version, builder) in PROMPTS.items():
            if (
                token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_CALL
                > max_cost_usd
            ):
                raise RuntimeError("cost上限へ達する前に比較を完了できません")
            error = None
            predicted_label = None
            response_data = None
            case_input = 0
            case_output = 0
            try:
                result = provider.generate_structured(
                    builder(
                        case["question"],
                        case["evidence"],
                        case["generated_answer"],
                    ),
                    schema,
                )
                response_data = result.data
                case_input = result.input_tokens
                case_output = result.output_tokens
                predicted_label = derive_label(
                    parse_classification_output(response_data).factors
                )
            except Exception as exception:
                error = f"{type(exception).__name__}: {exception}"
            input_tokens += case_input
            output_tokens += case_output
            records.append(
                {
                    "case_id": case["case_id"],
                    "modality": case["modality"],
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
            )
            if error:
                break
        if records[-1]["error"]:
            break

    summary = summarize(records, len(cases))
    bundle = {
        "dataset": {
            "path": str(dataset_path.relative_to(BASE_DIR)),
            "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "version": dataset["dataset_version"],
            "evaluation_mode": dataset["evaluation_mode"],
        },
        "model": CLASSIFIER_MODEL_NAME,
        "retry_count": 0,
        "max_logical_external_calls": max_logical_external_calls,
        "max_cost_usd": max_cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "summary": summary,
        "records": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, bundle)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()
    bundle = run_comparison(
        dataset_path=args.dataset.resolve(),
        output_path=args.output.resolve(),
        max_logical_external_calls=args.max_logical_external_calls,
        max_cost_usd=args.max_cost_usd,
    )
    print(json.dumps(bundle["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
