"""Bounded baseline/candidate pilot for answer-output-v2 and deadline calculation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME
from eval.evaluate_visual_answers import token_cost_usd
from src.contracts import IndexableElement, SearchHit
from src.llm_provider import GeminiProvider
from src.query_service import (
    CLASSIFICATION_PROMPT_V2_VERSION,
    CLASSIFICATION_PROMPT_VERSION,
    answer_question,
    build_classification_prompt,
    build_classification_prompt_v2,
    load_schema,
)
from src.temporal_evidence import (
    ANSWER_CONTRACT_V2_PROMPT_VERSION,
    TEMPORAL_GENERATION_PROMPT_VERSION,
    build_answer_contract_v2_prompt,
    build_temporal_generation_prompt,
)


BASELINE_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CANDIDATE_SCHEMA = BASE_DIR / "design/schemas/answer-output-v2.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
MAX_LOGICAL_EXTERNAL_CALLS = 48
RESERVE_USD_PER_VARIANT = 0.0015


SCENARIOS = (
    {
        "id": "ACV2-D01",
        "group": "date",
        "question": "2027年10月10日に受験しました。提出期限の具体的な日付と時刻はいつですか。",
        "evidence": "提出期限は、受験日の翌日を1日目として20暦日目の正午までとする。",
        "expected_label": "根拠十分",
        "required": (r"2027年10月30日正午",),
        "condition_type": None,
        "date_calculation": True,
    },
    {
        "id": "ACV2-D02",
        "group": "date",
        "question": "2028年2月28日に届出しました。翌日を1日目とする1暦日目、17時までの期限はいつですか。",
        "evidence": "届出日の翌日を1日目とし、1暦日目の17時までに補足資料を提出する。",
        "expected_label": "根拠十分",
        "required": (r"2028年2月29日17時00分",),
        "condition_type": None,
        "date_calculation": True,
    },
    {
        "id": "ACV2-D03",
        "group": "date",
        "question": "2027年12月31日に承認されました。翌日を1日目とする1暦日目の期限はいつですか。",
        "evidence": "承認日の翌日を1日目として1暦日目までに登録する。",
        "expected_label": "根拠十分",
        "required": (r"2028年1月1日",),
        "condition_type": None,
        "date_calculation": True,
    },
    {
        "id": "ACV2-D04",
        "group": "date",
        "question": "2027年5月15日に受理されました。当日を1日目とする10暦日目の期限はいつですか。",
        "evidence": "受理日当日を1日目として10暦日目までに処理を完了する。",
        "expected_label": "根拠十分",
        "required": (r"2027年5月24日",),
        "condition_type": None,
        "date_calculation": True,
    },
    {
        "id": "ACV2-D05",
        "group": "date",
        "question": "2027年1月31日に申請しました。翌日を1日目とする30暦日目の期限はいつですか。",
        "evidence": "申請日の翌日を1日目として30暦日目までに確認書を出す。",
        "expected_label": "根拠十分",
        "required": (r"2027年3月2日",),
        "condition_type": None,
        "date_calculation": True,
    },
    {
        "id": "ACV2-D06",
        "group": "date",
        "question": "2027/6/1に利用しました。翌日から数えて14暦日目、17時までの申込期限を教えてください。",
        "evidence": "利用日の翌日を1日目として14暦日目の17時までに申し込む。",
        "expected_label": "根拠十分",
        "required": (r"2027年6月15日17時00分",),
        "condition_type": None,
        "date_calculation": True,
    },
    {
        "id": "ACV2-M01",
        "group": "condition",
        "question": "書庫整理奨励金は一箱いくらですか。",
        "evidence": "書庫巡回加算は一区画800円とする。書庫整理奨励金は別規程で定める。",
        "expected_label": "文書不足",
        "required": (r"(根拠では回答を確認できません|文書不足)",),
        "condition_type": "missing_document",
        "date_calculation": False,
    },
    {
        "id": "ACV2-M02",
        "group": "condition",
        "question": "承認番号はありますが発行日時が不明です。支払を確定できますか。",
        "evidence": "承認番号の発行が業務実施前であることを確認できない場合、発行日時を照会し認定を保留する。",
        "expected_label": "判断要",
        "required": (r"(発行日時|認定を保留|確認が必要)",),
        "condition_type": "case_fact",
        "date_calculation": False,
    },
    {
        "id": "ACV2-M03",
        "group": "condition",
        "question": "災害による提出遅延があります。今回、例外として支給対象に認められますか。",
        "evidence": "災害等の例外事情がある場合、制度所管課が事情を総合考慮して支給可否を決定する。",
        "expected_label": "判断要",
        "required": (r"(制度所管課|総合考慮|確認が必要|支給可否)",),
        "condition_type": "policy_judgment",
        "date_calculation": False,
    },
    {
        "id": "ACV2-M04",
        "group": "condition",
        "question": "基準日を指定しない場合、旧通知と新通知のどちらの上限額を使いますか。",
        "evidence": "旧通知は上限5,000円、新通知は上限6,000円とする。新通知の施行日は2027年10月1日である。",
        "expected_label": "判断要",
        "required": (r"(基準日|適用する文書版|確認が必要)",),
        "condition_type": "case_fact",
        "date_calculation": False,
    },
    {
        "id": "ACV2-C01",
        "group": "control",
        "question": "通常の支給額はいくらですか。",
        "evidence": "通常の支給額は月額3,000円とする。",
        "expected_label": "根拠十分",
        "required": (r"3,?000円",),
        "condition_type": None,
        "date_calculation": False,
    },
    {
        "id": "ACV2-C02",
        "group": "control",
        "question": "2027年10月1日施行の新通知では補助上限はいくらですか。",
        "evidence": "新通知は2027年10月1日に施行し、補助上限を6,000円とする。",
        "expected_label": "根拠十分",
        "required": (r"6,?000円",),
        "condition_type": None,
        "date_calculation": False,
    },
)


class StaticIndex:
    def __init__(self, hits: list[SearchHit]):
        self.hits = hits

    def search(self, _vector: list[float], limit: int) -> list[SearchHit]:
        return self.hits[:limit]


@dataclass
class PilotLogger:
    request_id: UUID = field(default_factory=uuid4)
    generation: dict[str, Any] = field(default_factory=dict)
    classification: dict[str, Any] = field(default_factory=dict)
    answer_result: dict[str, Any] = field(default_factory=dict)

    def start_request(self, _question: str) -> UUID:
        return self.request_id

    def record_retrieval(self, _request_id: UUID, _hits: list[SearchHit]) -> None:
        return None

    def record_generation_attempt(self, _request_id: UUID, **kwargs) -> UUID:
        self.generation = kwargs
        return uuid4()

    def record_classification_attempt(self, _request_id: UUID, **kwargs) -> UUID:
        if kwargs.get("prompt_version") == "answer-classification-v1":
            self.classification = kwargs
        return uuid4()

    def record_answer_result(self, _request_id: UUID, **kwargs) -> UUID:
        self.answer_result = kwargs
        return uuid4()


def _element(scenario: dict[str, Any]) -> IndexableElement:
    scenario_id = scenario["id"]
    return IndexableElement(
        id=uuid5(NAMESPACE_URL, f"answer-contract-element:{scenario_id}"),
        document_id=uuid5(NAMESPACE_URL, f"answer-contract-document:{scenario_id}"),
        version_id=uuid5(NAMESPACE_URL, f"answer-contract-version:{scenario_id}"),
        document_name=f"回答契約検証文書 {scenario_id}",
        heading="検証規定",
        content=scenario["evidence"],
    )


def _provider_error(error: str) -> bool:
    lowered = error.lower()
    return any(
        marker in lowered
        for marker in ("429", "503", "unavailable", "resource_exhausted", "api")
    )


def _content_ok(answer: str, patterns: tuple[str, ...]) -> bool:
    return all(re.search(pattern, answer) for pattern in patterns)


def _contract_ok(
    scenario: dict[str, Any], variant: str, generation_data: dict[str, Any]
) -> bool:
    if variant == "baseline":
        return True
    calculations = generation_data.get("date_calculations", [])
    conditions = generation_data.get("missing_conditions", [])
    if scenario["date_calculation"]:
        return len(calculations) == 1 and not conditions
    if scenario["condition_type"] is not None:
        return (
            len(conditions) >= 1
            and scenario["condition_type"] in {item.get("type") for item in conditions}
            and not calculations
        )
    return not calculations and not conditions


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-logical-external-calls", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument("--reuse-dir", type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"評価出力は上書きしません: {args.output_dir}")
    if args.max_logical_external_calls > MAX_LOGICAL_EXTERNAL_CALLS:
        raise ValueError("このpilotのlogical external call上限は48です")
    reused_baselines: dict[str, dict[str, Any]] = {}
    if args.reuse_dir is not None:
        source_records = args.reuse_dir / "records.jsonl"
        if not source_records.exists():
            raise FileNotFoundError(f"再利用元recordsがありません: {source_records}")
        scenario_by_id = {scenario["id"]: scenario for scenario in SCENARIOS}
        for line in source_records.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            scenario = scenario_by_id.get(record.get("scenario_id"))
            if (
                scenario is not None
                and record.get("variant") == "baseline"
                and record.get("question") == scenario["question"]
                and not record.get("error")
            ):
                reused_baselines[scenario["id"]] = {
                    **record,
                    "execution_source": "REUSED_BASELINE",
                }
    pending_variants = len(SCENARIOS) + (len(SCENARIOS) - len(reused_baselines))
    if args.max_logical_external_calls < pending_variants * 2:
        raise ValueError(
            f"未実行{pending_variants} variantsには{pending_variants * 2} callsが必要です"
        )
    if args.max_cost_usd < pending_variants * RESERVE_USD_PER_VARIANT:
        raise ValueError("費用上限が安全予約額を下回っています")

    args.output_dir.mkdir(parents=True)
    records_path = args.output_dir / "records.jsonl"
    manifest = {
        "experiment": "answer-contract-v2-paired-pilot-v1",
        "scenario_count": len(SCENARIOS),
        "variants": ["baseline", "candidate"],
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "max_logical_external_calls": args.max_logical_external_calls,
        "max_cost_usd": args.max_cost_usd,
        "retry_count": 0,
        "sealed_holdout_accessed": False,
        "gold_adjudication": {
            "ACV2-M03": "質問を実際の例外適用可否へ変更し、policy judgmentの反対例にした",
            "ACV2-M04": "基準日自体の欠落はversion conflictではなくcase factとした",
        },
        "baseline_schema": str(BASELINE_SCHEMA.relative_to(BASE_DIR)),
        "candidate_schema": str(CANDIDATE_SCHEMA.relative_to(BASE_DIR)),
        "stop_conditions": ["provider error", "cost reserve exhausted", "call limit"],
        "reuse": (
            {
                "source_dir": str(args.reuse_dir),
                "source_records_sha256": _sha256(args.reuse_dir / "records.jsonl"),
                "reused_baseline_ids": sorted(reused_baselines),
            }
            if args.reuse_dir is not None
            else None
        ),
    }
    _write_json(args.output_dir / "run_manifest.json", manifest)

    generator = GeminiProvider(LLM_MODEL_NAME)
    classifier = GeminiProvider(CLASSIFIER_MODEL_NAME)
    records = list(reused_baselines.values())
    if records:
        with records_path.open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    logical_calls = 0
    input_tokens = 0
    output_tokens = 0
    stop_reason = "COMPLETED"

    variants = (
        (
            "baseline",
            BASELINE_SCHEMA,
            build_temporal_generation_prompt,
            TEMPORAL_GENERATION_PROMPT_VERSION,
        ),
        (
            "candidate",
            CANDIDATE_SCHEMA,
            build_answer_contract_v2_prompt,
            ANSWER_CONTRACT_V2_PROMPT_VERSION,
        ),
    )
    for scenario in SCENARIOS:
        element = _element(scenario)
        hit = SearchHit(element=element, score=1.0, rank=1)
        for variant, schema_path, prompt_builder, prompt_version in variants:
            if variant == "baseline" and scenario["id"] in reused_baselines:
                continue
            if logical_calls + 2 > args.max_logical_external_calls:
                stop_reason = "CALL_LIMIT_REACHED"
                break
            if (
                token_cost_usd(input_tokens, output_tokens)
                + RESERVE_USD_PER_VARIANT
                > args.max_cost_usd
            ):
                stop_reason = "COST_LIMIT_REACHED"
                break
            logger = PilotLogger()
            result = None
            error = ""
            started = time.perf_counter()
            try:
                result = answer_question(
                    scenario["question"],
                    embed_query=lambda _question: [1.0],
                    vector_index=StaticIndex([hit]),
                    generator=generator,
                    classifier=classifier,
                    event_logger=logger,
                    answer_schema=load_schema(schema_path),
                    classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                    top_k=1,
                    generation_prompt_builder=prompt_builder,
                    generation_prompt_version=prompt_version,
                    classification_prompt_builder=(
                        build_classification_prompt_v2
                        if variant == "candidate"
                        else build_classification_prompt
                    ),
                    classification_prompt_version=(
                        CLASSIFICATION_PROMPT_V2_VERSION
                        if variant == "candidate"
                        else CLASSIFICATION_PROMPT_VERSION
                    ),
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"

            generation_input = int(logger.generation.get("input_tokens", 0))
            generation_output = int(logger.generation.get("output_tokens", 0))
            classification_input = int(logger.classification.get("input_tokens", 0))
            classification_output = int(
                logger.classification.get("output_tokens", 0)
            )
            scenario_input = generation_input + classification_input
            scenario_output = generation_output + classification_output
            input_tokens += scenario_input
            output_tokens += scenario_output
            logical_calls += int(bool(logger.generation)) + int(
                bool(logger.classification)
            )
            generation_data = logger.generation.get("response_data") or {}
            answer = result.get("answer", "") if result else ""
            execution_ok = bool(result)
            classification_ok = execution_ok and (
                result.get("answer_label") == scenario["expected_label"]
            )
            content_ok = execution_ok and _content_ok(answer, scenario["required"])
            contract_ok = execution_ok and _contract_ok(
                scenario, variant, generation_data
            )
            semantic_status_ok = execution_ok and (
                result.get("answer_status") == "SUCCESS"
            )
            record = {
                "scenario_id": scenario["id"],
                "group": scenario["group"],
                "variant": variant,
                "question": scenario["question"],
                "expected_label": scenario["expected_label"],
                "predicted_label": result.get("answer_label") if result else None,
                "answer_status": result.get("answer_status") if result else None,
                "invariant_code": result.get("invariant_code") if result else None,
                "execution_ok": execution_ok,
                "classification_ok": classification_ok,
                "content_ok": content_ok,
                "contract_ok": contract_ok,
                "semantic_status_ok": semantic_status_ok,
                "composite_ok": all(
                    (
                        execution_ok,
                        classification_ok,
                        content_ok,
                        contract_ok,
                        semantic_status_ok,
                    )
                ),
                "answer": answer,
                "generation_response_data": generation_data,
                "classification_factors": logger.classification.get("factors"),
                "input_tokens": scenario_input,
                "output_tokens": scenario_output,
                "estimated_cost_usd": token_cost_usd(
                    scenario_input, scenario_output
                ),
                "elapsed_seconds": time.perf_counter() - started,
                "error": error or None,
                "execution_source": "CURRENT_RUN",
            }
            records.append(record)
            with records_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                f"{scenario['id']} {variant}: composite={record['composite_ok']} "
                f"label={record['predicted_label']} error={error or 'none'}"
            )
            if error:
                stop_reason = (
                    "PROVIDER_ERROR_FAIL_FAST"
                    if _provider_error(error)
                    else "CANDIDATE_ERROR_FAIL_FAST"
                )
                break
        if stop_reason != "COMPLETED":
            break

    by_key = {(row["scenario_id"], row["variant"]): row for row in records}
    paired_ids = [
        scenario["id"]
        for scenario in SCENARIOS
        if (scenario["id"], "baseline") in by_key
        and (scenario["id"], "candidate") in by_key
    ]
    improvements = [
        scenario_id
        for scenario_id in paired_ids
        if not by_key[(scenario_id, "baseline")]["composite_ok"]
        and by_key[(scenario_id, "candidate")]["composite_ok"]
    ]
    regressions = [
        scenario_id
        for scenario_id in paired_ids
        if by_key[(scenario_id, "baseline")]["composite_ok"]
        and not by_key[(scenario_id, "candidate")]["composite_ok"]
    ]
    candidate = [row for row in records if row["variant"] == "candidate"]
    candidate_by_group = {
        group: {
            "success": sum(
                row["composite_ok"] for row in candidate if row["group"] == group
            ),
            "total": sum(row["group"] == group for row in candidate),
        }
        for group in ("date", "condition", "control")
    }
    gate_passed = (
        stop_reason == "COMPLETED"
        and not regressions
        and candidate_by_group["date"] == {"success": 6, "total": 6}
        and candidate_by_group["condition"] == {"success": 4, "total": 4}
        and candidate_by_group["control"] == {"success": 2, "total": 2}
    )
    summary = {
        "stop_reason": stop_reason,
        "completed_records": len(records),
        "paired_scenarios": len(paired_ids),
        "logical_external_calls": logical_calls,
        "reused_baselines": len(reused_baselines),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": args.max_cost_usd,
        "baseline_composite_success": sum(
            row["composite_ok"] for row in records if row["variant"] == "baseline"
        ),
        "candidate_composite_success": sum(
            row["composite_ok"] for row in candidate
        ),
        "candidate_by_group": candidate_by_group,
        "improvements": improvements,
        "regressions": regressions,
        "gate_passed": gate_passed,
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if stop_reason == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
