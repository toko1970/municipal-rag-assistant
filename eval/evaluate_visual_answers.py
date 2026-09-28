"""Run a bounded visual-answer baseline without opening the sealed holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from qdrant_client import QdrantClient

from config import BASE_DIR, CLASSIFIER_MODEL_NAME, LLM_MODEL_NAME
from src.asset_store import LocalAssetStore, VisualEvidenceAsset
from src.embeddings import get_embeddings
from src.ingestion import contextual_heading_document_text
from src.llm_provider import GeminiProvider
from src.qdrant_index import QdrantVectorIndex
from src.query_service import (
    CLASSIFICATION_PROMPT_VERSION,
    GENERATION_PROMPT_VERSION,
    answer_question,
    load_schema,
)
from src.visual_ingestion import build_visual_element, render_pdf_page


DEFAULT_DATASET = BASE_DIR / "eval/visual_fixtures/development_evaluation_set.json"
DEFAULT_FIXTURE_MANIFEST = (
    BASE_DIR / "eval/visual_fixtures/manifests/development_manifest.json"
)
ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = (
    BASE_DIR / "design/schemas/classification-output-v1.schema.json"
)
PRICING_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
PRICE_VERIFIED_ON = "2026-09-28"
INPUT_USD_PER_MILLION = 0.25
OUTPUT_USD_PER_MILLION = 1.50
LABELS = {
    "grounded": "根拠十分",
    "needs_judgment": "判断要",
    "insufficient_documents": "文書不足",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BASE_DIR))
    except ValueError:
        return str(resolved)


def token_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * INPUT_USD_PER_MILLION
        + output_tokens * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


@dataclass
class EvaluationEventLogger:
    """Capture provider usage while keeping evaluation rows out of product logs."""

    generation_attempts: list[dict[str, Any]] = field(default_factory=list)
    classification_attempts: list[dict[str, Any]] = field(default_factory=list)

    def start_request(self, _question: str) -> UUID:
        return uuid4()

    def record_retrieval(self, _request_id: UUID, _hits) -> None:
        return None

    def record_generation_attempt(self, _request_id: UUID, **kwargs) -> UUID:
        self.generation_attempts.append(kwargs)
        return uuid4()

    def record_classification_attempt(self, _request_id: UUID, **kwargs) -> UUID:
        self.classification_attempts.append(kwargs)
        return uuid4()

    def record_answer_result(self, _request_id: UUID, **_kwargs) -> UUID:
        return uuid4()


@dataclass(frozen=True)
class PreparedVisualCorpus:
    index: QdrantVectorIndex
    assets: dict[UUID, VisualEvidenceAsset]
    fixture_by_element: dict[str, str]
    embedding_batch_calls: int


def prepare_visual_corpus(
    fixture_manifest_path: Path,
    asset_dir: Path,
    embeddings,
) -> PreparedVisualCorpus:
    """Build an isolated in-memory Qdrant corpus from reviewed development gold."""

    manifest = _read_json(fixture_manifest_path)
    store = LocalAssetStore(asset_dir)
    elements = []
    assets: dict[UUID, VisualEvidenceAsset] = {}
    fixture_by_element: dict[str, str] = {}
    for fixture in manifest["fixtures"]:
        fixture_id = fixture["fixture_id"]
        pdf_path = BASE_DIR / fixture["document"]["path"]
        extraction = _read_json(BASE_DIR / fixture["gold"]["path"])
        page = render_pdf_page(pdf_path, int(extraction["page"]))
        extraction["source_image_sha256"] = page.sha256
        element = build_visual_element(
            pdf_path=pdf_path,
            document_key=f"visual-eval-{fixture_id}",
            document_name=str(extraction["title"]),
            extraction=extraction,
        )
        stored = store.put_page_image(
            document_key=f"visual-eval-{fixture_id}",
            page_number=page.page_number,
            content=page.png,
        )
        assets[element.id] = VisualEvidenceAsset(
            element_id=element.id,
            storage_uri=stored.storage_uri,
            mime_type=stored.mime_type,
            page_number=page.page_number,
            sha256=stored.sha256,
            bbox=dict(extraction["bbox"]),
        )
        fixture_by_element[str(element.id)] = fixture_id
        elements.append(element)

    vectors = embeddings.embed_documents(
        [contextual_heading_document_text(element) for element in elements],
        task_type="RETRIEVAL_DOCUMENT",
    )
    client = QdrantClient(":memory:")
    index = QdrantVectorIndex(
        client=client, collection_name="visual_answer_development_v1"
    )
    index.ensure_collection(len(vectors[0]))
    index.upsert(elements, vectors, "gemini:visual-answer-development-v1")
    return PreparedVisualCorpus(index, assets, fixture_by_element, 1)


def _usage(result: dict[str, Any]) -> tuple[int, int]:
    generation = result.get("generation") or {}
    classification = result.get("classification") or {}
    return (
        int(generation.get("input_tokens", 0))
        + int(classification.get("input_tokens", 0)),
        int(generation.get("output_tokens", 0))
        + int(classification.get("output_tokens", 0)),
    )


def _portable_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    without_binary = []
    for reference in references:
        item = dict(reference)
        visual_asset = item.get("visual_asset")
        if isinstance(visual_asset, dict):
            visual_asset = dict(visual_asset)
            visual_asset.pop("content", None)
            item["visual_asset"] = visual_asset
        without_binary.append(item)
    return _json_safe(without_binary)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def evaluate_visual_answers(
    *,
    dataset: dict[str, Any],
    output_dir: Path,
    generate_fn: Callable[[str], dict[str, Any]],
    fixture_by_element: dict[str, str],
    max_scenarios: int,
    max_cost_usd: float,
    per_scenario_cost_reserve_usd: float = 0.01,
    resume: bool = False,
) -> dict[str, Any]:
    if output_dir.exists() and not resume:
        raise FileExistsError(f"評価出力は上書きしません: {output_dir}")
    scenarios = dataset["scenarios"]
    if max_scenarios < 1 or max_scenarios > len(scenarios):
        raise ValueError("max_scenariosがdataset件数の範囲外です")
    if max_cost_usd <= 0:
        raise ValueError("max_cost_usdは0より大きい必要があります")
    if per_scenario_cost_reserve_usd <= 0:
        raise ValueError("per_scenario_cost_reserve_usdは0より大きい必要があります")

    output_dir.mkdir(parents=True, exist_ok=resume)
    records_path = output_dir / "records.jsonl"
    records = (
        [json.loads(line) for line in records_path.read_text().splitlines() if line]
        if resume and records_path.exists()
        else []
    )
    completed_ids = {record["scenario_id"] for record in records}
    input_tokens = sum(int(record.get("input_tokens", 0)) for record in records)
    output_tokens = sum(int(record.get("output_tokens", 0)) for record in records)
    stop_reason = "SCENARIO_LIMIT_REACHED"
    for scenario in scenarios[:max_scenarios]:
        if scenario["scenario_id"] in completed_ids:
            continue
        if (
            token_cost_usd(input_tokens, output_tokens)
            + per_scenario_cost_reserve_usd
            > max_cost_usd
        ):
            stop_reason = "COST_LIMIT_REACHED"
            break
        started = time.perf_counter()
        try:
            result = generate_fn(str(scenario["question"]))
            scenario_input, scenario_output = _usage(result)
            input_tokens += scenario_input
            output_tokens += scenario_output
            retrieved_fixtures = list(
                dict.fromkeys(
                    fixture_by_element.get(str(ref.get("element_id")), "")
                    for ref in result.get("references", [])
                    if fixture_by_element.get(str(ref.get("element_id")))
                )
            )
            expected_fixtures = list(scenario["fixture_ids"])
            record = {
                "scenario_id": scenario["scenario_id"],
                "question": scenario["question"],
                "difficulty": scenario["difficulty"],
                "expected_classification": scenario["expected_classification"],
                "predicted_label": result.get("answer_label"),
                "classification_ok": result.get("answer_label")
                == LABELS[scenario["expected_classification"]],
                "expected_fixture_ids": expected_fixtures,
                "retrieved_fixture_ids": retrieved_fixtures,
                "required_fixture_retrieved": all(
                    fixture in retrieved_fixtures for fixture in expected_fixtures
                ),
                "expected_answer_key": scenario["expected_answer_key"],
                "required_evidence": scenario["required_evidence"],
                "answer": result.get("answer", ""),
                "claims": _json_safe(result.get("claims", [])),
                "references": _portable_references(result.get("references", [])),
                "content_review_status": "pending",
                "input_tokens": scenario_input,
                "output_tokens": scenario_output,
                "cost_usd": token_cost_usd(scenario_input, scenario_output),
                "elapsed_seconds": time.perf_counter() - started,
                "error": None,
            }
        except Exception as error:
            record = {
                "scenario_id": scenario["scenario_id"],
                "question": scenario["question"],
                "expected_classification": scenario["expected_classification"],
                "content_review_status": "blocked_by_error",
                "elapsed_seconds": time.perf_counter() - started,
                "error": f"{type(error).__name__}: {error}",
            }
        records.append(record)
        with records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        if record["error"]:
            stop_reason = "ERROR_FAIL_FAST"
            break

    completed = [record for record in records if not record["error"]]
    summary = {
        "dataset_version": dataset["dataset_version"],
        "split": dataset["split"],
        "scenario_limit": max_scenarios,
        "completed_count": len(completed),
        "error_count": len(records) - len(completed),
        "classification_correct": sum(
            bool(record.get("classification_ok")) for record in completed
        ),
        "required_fixture_retrieved": sum(
            bool(record.get("required_fixture_retrieved")) for record in completed
        ),
        "content_review_pending": len(completed),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
        "max_cost_usd": max_cost_usd,
        "per_scenario_cost_reserve_usd": per_scenario_cost_reserve_usd,
        "stop_reason": stop_reason,
        "records_path": "records.jsonl",
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--fixture-manifest", type=Path, default=DEFAULT_FIXTURE_MANIFEST
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-scenarios", type=int, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument(
        "--per-scenario-cost-reserve-usd", type=float, default=0.01
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--scenario-id",
        action="append",
        help="指定したdevelopment scenarioだけを実行する。複数回指定可能",
    )
    args = parser.parse_args()

    dataset = _read_json(args.dataset)
    if dataset.get("split") != "development":
        parser.error("このrunnerはdevelopment splitだけを許可します")
    if args.scenario_id:
        requested = set(args.scenario_id)
        selected = [
            scenario
            for scenario in dataset["scenarios"]
            if scenario["scenario_id"] in requested
        ]
        found = {scenario["scenario_id"] for scenario in selected}
        if found != requested:
            parser.error(f"scenario IDが見つかりません: {sorted(requested - found)}")
        dataset = {**dataset, "scenarios": selected, "scenario_count": len(selected)}
    output_dir = args.output_dir.resolve()
    run_manifest = {
        "dataset_path": _portable_path(args.dataset),
        "dataset_sha256": _sha256(args.dataset),
        "fixture_manifest_path": _portable_path(args.fixture_manifest),
        "fixture_manifest_sha256": _sha256(args.fixture_manifest),
        "split": "development",
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "generation_prompt_version": GENERATION_PROMPT_VERSION,
        "classification_prompt_version": CLASSIFICATION_PROMPT_VERSION,
        "embedding_model": "gemini-embedding-001",
        "scenario_ids": args.scenario_id or "all",
        "max_scenarios": args.max_scenarios,
        "max_logical_external_calls": 1 + args.max_scenarios * 3,
        "retry_count": 0,
        "max_cost_usd": args.max_cost_usd,
        "per_scenario_cost_reserve_usd": args.per_scenario_cost_reserve_usd,
        "pricing": {
            "source": PRICING_SOURCE,
            "verified_on": PRICE_VERIFIED_ON,
            "input_usd_per_million_tokens": INPUT_USD_PER_MILLION,
            "output_usd_per_million_tokens": OUTPUT_USD_PER_MILLION,
        },
        "sealed_holdout_accessed": False,
    }
    if output_dir.exists() and not args.resume:
        raise FileExistsError(f"評価出力は上書きしません: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=args.resume)
    manifest_path = output_dir / "run_manifest.json"
    if args.resume:
        previous = _read_json(manifest_path)
        for key in (
            "dataset_sha256",
            "fixture_manifest_sha256",
            "generator_model",
            "classifier_model",
            "max_scenarios",
            "max_cost_usd",
            "per_scenario_cost_reserve_usd",
        ):
            if previous.get(key) != run_manifest.get(key):
                raise ValueError(f"resume条件が元runと一致しません: {key}")
    else:
        _write_json(manifest_path, run_manifest)

    embeddings = get_embeddings()
    with tempfile.TemporaryDirectory(prefix="visual-answer-assets-") as asset_dir:
        corpus = prepare_visual_corpus(
            args.fixture_manifest, Path(asset_dir), embeddings
        )
        generator = GeminiProvider(LLM_MODEL_NAME)
        classifier = GeminiProvider(CLASSIFIER_MODEL_NAME)

        def generate(question: str) -> dict[str, Any]:
            return answer_question(
                question,
                embed_query=embeddings.embed_query,
                vector_index=corpus.index,
                generator=generator,
                classifier=classifier,
                event_logger=EvaluationEventLogger(),
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                top_k=5,
                visual_asset_loader=lambda ids: [
                    corpus.assets[element_id]
                    for element_id in ids
                    if element_id in corpus.assets
                ],
                max_visual_assets=3,
            )

        # The manifest stays next to the resumable, append-only evaluation records.
        evaluation_dir = output_dir / "evaluation"
        summary = evaluate_visual_answers(
            dataset=dataset,
            output_dir=evaluation_dir,
            generate_fn=generate,
            fixture_by_element=corpus.fixture_by_element,
            max_scenarios=args.max_scenarios,
            max_cost_usd=args.max_cost_usd,
            per_scenario_cost_reserve_usd=args.per_scenario_cost_reserve_usd,
            resume=args.resume,
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
