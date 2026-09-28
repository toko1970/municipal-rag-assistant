"""Create one bounded visual holdout prediction bundle without reading gold."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import fitz
from qdrant_client import QdrantClient

from config import (
    BASE_DIR,
    CLASSIFIER_MODEL_NAME,
    EMBEDDING_MODEL_NAME,
    LLM_MODEL_NAME,
    QDRANT_COLLECTION_NAME,
    TOP_K,
)
from eval.evaluate_visual_answers import EvaluationEventLogger, token_cost_usd
from eval.validate_visual_fixture import load_json, verify_hash
from eval.validate_visual_holdout_protocol import (
    CANDIDATE_CONFIG_PATH,
    validate_public_manifest,
)
from src.asset_store import LocalAssetStore, VisualEvidenceAsset
from src.embedding_representation import contextual_heading_document_text
from src.embeddings import get_embeddings
from src.llm_provider import GeminiProvider
from src.qdrant_index import QdrantVectorIndex
from src.query_service import answer_question, load_schema
from src.visual_extractor import extract_visual_candidate
from src.visual_ingestion import (
    build_visual_element,
    load_visual_schema,
    render_pdf_page,
)
from src.visual_validation import validate_gold


PUBLIC_MANIFEST = BASE_DIR / "eval/visual_holdout/public_manifest.json"
QUESTIONS = BASE_DIR / "eval/visual_holdout/questions.json"
ANSWER_SCHEMA = BASE_DIR / "design/schemas/answer-output-v1.schema.json"
CLASSIFICATION_SCHEMA = BASE_DIR / "design/schemas/classification-output-v1.schema.json"
DOCUMENT_COUNT = 6
SCENARIO_COUNT = 20
MAX_LOGICAL_EXTERNAL_CALLS = 67
DEFAULT_MAX_COST_USD = 0.35
RESERVE_USD_PER_ITEM = 0.01
KIND_HINTS = {
    "process_flow": "flowchart",
    "decision_flow": "flowchart",
    "table": "table",
    "form": "form",
    "timeline": "timeline",
    "revision_comparison": "table",
}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _portable_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    portable = []
    for reference in references:
        item = dict(reference)
        if isinstance(item.get("visual_asset"), dict):
            item["visual_asset"] = dict(item["visual_asset"])
            item["visual_asset"].pop("content", None)
        portable.append(item)
    return _json_safe(portable)


def load_frozen_candidate() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = validate_public_manifest(PUBLIC_MANIFEST, BASE_DIR)
    config = load_json(BASE_DIR / CANDIDATE_CONFIG_PATH)
    expected = {
        "generator model": (config["pipeline"]["generation"]["model"], LLM_MODEL_NAME),
        "classifier model": (
            config["pipeline"]["classification"]["model"],
            CLASSIFIER_MODEL_NAME,
        ),
        "embedding model": (
            config["pipeline"]["embedding"]["model"],
            EMBEDDING_MODEL_NAME,
        ),
        "collection": (
            config["pipeline"]["retrieval"]["collection"],
            QDRANT_COLLECTION_NAME,
        ),
        "top_k": (config["pipeline"]["retrieval"]["top_k"], TOP_K),
    }
    mismatches = [
        f"{label}: frozen={frozen!r}, runtime={runtime!r}"
        for label, (frozen, runtime) in expected.items()
        if frozen != runtime
    ]
    if mismatches:
        raise ValueError("frozen candidateとruntime設定が一致しません: " + "; ".join(mismatches))
    return manifest, config


def build_execution_plan(
    manifest: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    return {
        "holdout_id": manifest["holdout_id"],
        "candidate_git_commit": manifest["candidate"]["git_commit"],
        "candidate_config_sha256": manifest["candidate"]["config_manifest_sha256"],
        "document_count": len(manifest["documents"]),
        "scenario_count": manifest["questions"]["count"],
        "logical_external_call_limit": MAX_LOGICAL_EXTERNAL_CALLS,
        "logical_external_calls": {
            "visual_extraction": DOCUMENT_COUNT,
            "document_embedding_batch": 1,
            "question_embedding": SCENARIO_COUNT,
            "answer_generation": SCENARIO_COUNT,
            "answer_classification": SCENARIO_COUNT,
        },
        "retry_count": config["execution_policy"]["retry_count"],
        "gold_available_to_runner": False,
        "max_cost_usd": DEFAULT_MAX_COST_USD,
        "minimum_reserved_cost_usd": (
            DOCUMENT_COUNT + SCENARIO_COUNT
        ) * RESERVE_USD_PER_ITEM,
    }


def verify_document_inputs(
    manifest: dict[str, Any], documents_dir: Path
) -> list[tuple[dict[str, Any], Path]]:
    """Verify only sealed PDFs. This function has no gold-directory parameter."""

    verified = []
    for document in manifest["documents"]:
        path = documents_dir / f"{document['document_id']}.pdf"
        if not path.is_file():
            raise ValueError(f"sealed PDFがありません: {document['document_id']}")
        verify_hash(path, document["sha256"], document["document_id"])
        with fitz.open(path) as pdf:
            if pdf.page_count != 1:
                raise ValueError(
                    f"holdout PDFは1 pageで固定します: {document['document_id']}"
                )
        verified.append((document, path))
    return verified


@dataclass(frozen=True)
class HoldoutCorpus:
    index: QdrantVectorIndex
    assets: dict[UUID, VisualEvidenceAsset]
    document_by_element: dict[str, str]
    extraction_records: list[dict[str, Any]]


def prepare_holdout_corpus(
    *,
    documents: list[tuple[dict[str, Any], Path]],
    extraction_dir: Path,
    asset_dir: Path,
    provider: GeminiProvider,
    embeddings: Any,
    max_cost_usd: float,
) -> HoldoutCorpus:
    store = LocalAssetStore(asset_dir)
    elements = []
    assets: dict[UUID, VisualEvidenceAsset] = {}
    document_by_element: dict[str, str] = {}
    records = []
    for document, pdf_path in documents:
        spent = token_cost_usd(
            sum(item["input_tokens"] for item in records),
            sum(item["output_tokens"] for item in records),
        )
        if spent + RESERVE_USD_PER_ITEM > max_cost_usd:
            raise RuntimeError("cost上限へ達する前に全PDFを抽出できません")
        document_id = document["document_id"]
        page = render_pdf_page(pdf_path, 1)
        started = time.perf_counter()
        candidate = extract_visual_candidate(
            page=page,
            kind_hint=KIND_HINTS[document["kind"]],
            provider=provider,
        )
        _write_json(extraction_dir / f"{document_id}.raw.json", candidate.raw_data)
        _write_json(extraction_dir / f"{document_id}.normalized.json", candidate.data)
        record = {
            "document_id": document_id,
            "public_kind": document["kind"],
            "predicted_kind": candidate.data.get("kind"),
            "provider": candidate.provider,
            "model": candidate.model,
            "prompt_version": candidate.prompt_version,
            "input_tokens": candidate.input_tokens,
            "output_tokens": candidate.output_tokens,
            "request_id": candidate.request_id,
            "elapsed_seconds": time.perf_counter() - started,
            "normalized_bbox_count": candidate.normalized_bbox_count,
            "normalized_structure_count": candidate.normalized_structure_count,
            "validation_errors": list(candidate.validation_errors),
        }
        records.append(record)
        if candidate.validation_errors:
            raise ValueError(
                f"visual extractionがschema検証に失敗しました: {document_id}"
            )
        element = build_visual_element(
            pdf_path=pdf_path,
            document_key=f"visual-holdout-{document_id}",
            document_name=str(candidate.data["title"]),
            extraction=candidate.data,
        )
        stored = store.put_page_image(
            document_key=f"visual-holdout-{document_id}",
            page_number=1,
            content=page.png,
        )
        assets[element.id] = VisualEvidenceAsset(
            element_id=element.id,
            storage_uri=stored.storage_uri,
            mime_type=stored.mime_type,
            page_number=1,
            sha256=stored.sha256,
            bbox=dict(candidate.data["bbox"]),
        )
        document_by_element[str(element.id)] = document_id
        elements.append(element)

    vectors = embeddings.embed_documents(
        [contextual_heading_document_text(element) for element in elements],
        task_type="RETRIEVAL_DOCUMENT",
    )
    index = QdrantVectorIndex(
        client=QdrantClient(":memory:"),
        collection_name="visual_sealed_holdout_prediction_v1",
    )
    index.ensure_collection(len(vectors[0]))
    index.upsert(elements, vectors, "gemini:visual-sealed-holdout-prediction-v1")
    return HoldoutCorpus(index, assets, document_by_element, records)


def _answer_usage(result: dict[str, Any]) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    for stage in ("generation", "classification"):
        usage = result.get(stage) or {}
        input_tokens += int(usage.get("input_tokens", 0))
        output_tokens += int(usage.get("output_tokens", 0))
    return input_tokens, output_tokens


def run_predictions(
    *,
    documents_dir: Path,
    output_dir: Path,
    max_cost_usd: float,
    max_logical_external_calls: int,
) -> tuple[dict[str, Any], str]:
    manifest, config = load_frozen_candidate()
    if manifest["state"] != "CANDIDATE_FROZEN":
        raise ValueError("prediction実行前のstateはCANDIDATE_FROZENである必要があります")
    plan = build_execution_plan(manifest, config)
    if max_logical_external_calls != MAX_LOGICAL_EXTERNAL_CALLS:
        raise ValueError(
            f"logical external call上限は{MAX_LOGICAL_EXTERNAL_CALLS}で固定します"
        )
    if max_cost_usd < plan["minimum_reserved_cost_usd"]:
        raise ValueError("cost上限が26 item分の事前予約額を下回っています")
    if output_dir.exists():
        raise FileExistsError(f"prediction出力は上書きしません: {output_dir}")

    documents = verify_document_inputs(manifest, documents_dir)
    questions = load_json(QUESTIONS)
    output_dir.mkdir(parents=True)
    extraction_dir = output_dir / "extraction"
    extraction_dir.mkdir()
    run_manifest = {
        **plan,
        "run_id": output_dir.name,
        "questions_sha256": manifest["questions"]["sha256"],
        "documents": [
            {"document_id": item["document_id"], "sha256": item["sha256"]}
            for item in manifest["documents"]
        ],
        "generator_model": LLM_MODEL_NAME,
        "classifier_model": CLASSIFIER_MODEL_NAME,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "top_k": TOP_K,
        "max_visual_assets": config["pipeline"]["generation"][
            "max_visual_assets"
        ],
        "sealed_documents_accessed": True,
        "sealed_gold_accessed": False,
        "max_cost_usd": max_cost_usd,
    }
    _write_json(output_dir / "run_manifest.json", run_manifest)

    embeddings = get_embeddings()
    provider = GeminiProvider(LLM_MODEL_NAME)
    classifier = GeminiProvider(CLASSIFIER_MODEL_NAME)
    predictions = []
    with tempfile.TemporaryDirectory(prefix="visual-holdout-assets-") as asset_dir:
        corpus = prepare_holdout_corpus(
            documents=documents,
            extraction_dir=extraction_dir,
            asset_dir=Path(asset_dir),
            provider=provider,
            embeddings=embeddings,
            max_cost_usd=max_cost_usd,
        )
        input_tokens = sum(item["input_tokens"] for item in corpus.extraction_records)
        output_tokens = sum(item["output_tokens"] for item in corpus.extraction_records)
        for scenario in questions["scenarios"]:
            if (
                token_cost_usd(input_tokens, output_tokens) + RESERVE_USD_PER_ITEM
                > max_cost_usd
            ):
                raise RuntimeError("cost上限へ達する前に全predictionを固定できません")
            started = time.perf_counter()
            result = answer_question(
                str(scenario["question"]),
                embed_query=embeddings.embed_query,
                vector_index=corpus.index,
                generator=provider,
                classifier=classifier,
                event_logger=EvaluationEventLogger(),
                answer_schema=load_schema(ANSWER_SCHEMA),
                classification_schema=load_schema(CLASSIFICATION_SCHEMA),
                top_k=TOP_K,
                visual_asset_loader=lambda ids: [
                    corpus.assets[element_id]
                    for element_id in ids
                    if element_id in corpus.assets
                ],
                max_visual_assets=config["pipeline"]["generation"][
                    "max_visual_assets"
                ],
            )
            scenario_input, scenario_output = _answer_usage(result)
            input_tokens += scenario_input
            output_tokens += scenario_output
            retrieved_document_ids = list(
                dict.fromkeys(
                    corpus.document_by_element.get(str(ref.get("element_id")), "")
                    for ref in result.get("references", [])
                    if corpus.document_by_element.get(str(ref.get("element_id")))
                )
            )
            predictions.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "question": scenario["question"],
                    "predicted_label": result.get("answer_label"),
                    "answer": result.get("answer", ""),
                    "claims": _json_safe(result.get("claims", [])),
                    "references": _portable_references(result.get("references", [])),
                    "retrieved_document_ids": retrieved_document_ids,
                    "input_tokens": scenario_input,
                    "output_tokens": scenario_output,
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )

    bundle = {
        "run_manifest": run_manifest,
        "extractions": corpus.extraction_records,
        "predictions": predictions,
        "summary": {
            "extraction_count": len(corpus.extraction_records),
            "prediction_count": len(predictions),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": token_cost_usd(input_tokens, output_tokens),
            "error_count": 0,
        },
    }
    bundle_path = output_dir / "predictions.json"
    _write_json(bundle_path, bundle)
    bundle_hash = _sha256(bundle_path)
    return bundle, bundle_hash


def freeze_failed_predictions(output_dir: Path) -> tuple[dict[str, Any], str]:
    """Freeze blocked outcomes after a fail-fast run, without another API call."""

    manifest, _config = load_frozen_candidate()
    run_manifest = load_json(output_dir / "run_manifest.json")
    if run_manifest.get("sealed_gold_accessed") is not False:
        raise ValueError("gold未参照のrunだけをfailureとして固定できます")
    bundle_path = output_dir / "predictions.json"
    if bundle_path.exists():
        raise FileExistsError(f"prediction bundleは上書きしません: {bundle_path}")

    extraction_records = []
    failed_document_id = None
    failure = None
    schema = load_visual_schema()
    for document in manifest["documents"]:
        document_id = document["document_id"]
        normalized_path = output_dir / "extraction" / f"{document_id}.normalized.json"
        raw_path = output_dir / "extraction" / f"{document_id}.raw.json"
        if not normalized_path.exists():
            break
        status = "VALID"
        error = None
        try:
            validate_gold(load_json(normalized_path), schema)
        except ValueError as exception:
            status = "INVALID"
            error = f"{type(exception).__name__}: {exception}"
            failed_document_id = document_id
            failure = error
        extraction_records.append(
            {
                "document_id": document_id,
                "status": status,
                "error": error,
                "normalized_path": str(normalized_path.relative_to(BASE_DIR)),
                "normalized_sha256": _sha256(normalized_path),
                "raw_path": str(raw_path.relative_to(BASE_DIR)),
                "raw_sha256": _sha256(raw_path),
            }
        )
        if error:
            break
    if failed_document_id is None:
        raise ValueError("固定対象の抽出失敗が見つかりません")

    questions = load_json(QUESTIONS)
    predictions = [
        {
            "scenario_id": scenario["scenario_id"],
            "question": scenario["question"],
            "status": "BLOCKED_BY_EXTRACTION_ERROR",
            "predicted_label": None,
            "answer": None,
            "claims": [],
            "references": [],
            "error": failure,
        }
        for scenario in questions["scenarios"]
    ]
    bundle = {
        "run_manifest": run_manifest,
        "extractions": extraction_records,
        "predictions": predictions,
        "summary": {
            "status": "ERROR_FAIL_FAST",
            "failed_stage": "visual_extraction",
            "failed_document_id": failed_document_id,
            "failure": failure,
            "extraction_attempt_count": len(extraction_records),
            "valid_extraction_count": sum(
                item["status"] == "VALID" for item in extraction_records
            ),
            "question_attempt_count": 0,
            "prediction_outcome_count": len(predictions),
            "answer_external_call_count": 0,
            "retry_count": 0,
            "sealed_gold_accessed": False,
            "token_usage_recoverable_after_fail_fast": False,
        },
    }
    _write_json(bundle_path, bundle)
    return bundle, _sha256(bundle_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="sealed contentへ触れず実行条件だけを表示する")
    run = subparsers.add_parser("run", help="sealed PDFからpredictionを1回だけ作る")
    run.add_argument("--sealed-documents-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--max-cost-usd", type=float, default=DEFAULT_MAX_COST_USD)
    run.add_argument(
        "--max-logical-external-calls",
        type=int,
        default=MAX_LOGICAL_EXTERNAL_CALLS,
    )
    freeze_failure = subparsers.add_parser(
        "freeze-failure",
        help="fail-fast出力を追加API callなしで20件のblocked outcomeとして固定する",
    )
    freeze_failure.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "plan":
        manifest, config = load_frozen_candidate()
        print(json.dumps(build_execution_plan(manifest, config), ensure_ascii=False))
        return 0
    if args.command == "freeze-failure":
        bundle, bundle_hash = freeze_failed_predictions(args.output_dir.resolve())
        print(
            json.dumps(
                {
                    "run_id": bundle["run_manifest"]["run_id"],
                    "prediction_outcome_count": bundle["summary"][
                        "prediction_outcome_count"
                    ],
                    "question_attempt_count": bundle["summary"][
                        "question_attempt_count"
                    ],
                    "sha256": bundle_hash,
                    "sealed_gold_accessed": False,
                },
                ensure_ascii=False,
            )
        )
        return 0
    bundle, bundle_hash = run_predictions(
        documents_dir=args.sealed_documents_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        max_cost_usd=args.max_cost_usd,
        max_logical_external_calls=args.max_logical_external_calls,
    )
    print(
        json.dumps(
            {
                "run_id": bundle["run_manifest"]["run_id"],
                "prediction_count": bundle["summary"]["prediction_count"],
                "sha256": bundle_hash,
                "sealed_gold_accessed": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
