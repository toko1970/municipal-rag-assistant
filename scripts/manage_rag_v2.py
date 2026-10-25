"""Management commands for the PostgreSQL and Qdrant RAG v2 slice."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from config import (
    ANSWER_GENERATION_FLOW,
    BASE_DIR,
    CLASSIFICATION_CONTRACT_VERSION,
    DATABASE_URL,
    LLM_MODEL_NAME,
)
from src.asset_backend import get_asset_store
from src.embeddings import get_embeddings
from src.ingestion import ingest_markdown_documents
from src.llm_provider import GeminiProvider
from src.persistence.database import get_engine
from src.persistence.repositories import PostgresDocumentRepository
from src.provider_retry import classify_provider_error, run_with_503_backoff
from src.qdrant_index import QdrantVectorIndex
from src.rag_v2 import generate_qdrant_answer
from src.visual_ingestion import ingest_visual_pdf
from src.visual_extractor import extract_visual_candidate
from src.visual_ingestion import render_pdf_page
from src.smoke_validation import SMOKE_CASES, SmokeVerdict, validate_smoke_result


CLOUD_SMOKE_QUESTION = SMOKE_CASES[0].question
VISUAL_DEVELOPMENT_MANIFEST = (
    BASE_DIR / "eval/visual_fixtures/manifests/development_manifest.json"
)

def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def migrate() -> None:
    configuration = Config(str(BASE_DIR / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(configuration, "head")


def health() -> dict[str, object]:
    with get_engine().connect() as connection:
        postgres_value = connection.scalar(select(1))
    qdrant = QdrantVectorIndex()
    collections = [item.name for item in qdrant.client.get_collections().collections]
    return {
        "postgres": postgres_value == 1,
        "qdrant": True,
        "qdrant_collections": collections,
    }


def ingest() -> dict[str, int]:
    repository = PostgresDocumentRepository(session_factory())
    return ingest_markdown_documents(repository, QdrantVectorIndex())


def rebuild_qdrant() -> dict[str, int]:
    index = QdrantVectorIndex()
    if index.client.collection_exists(index.collection_name):
        index.client.delete_collection(index.collection_name)
    repository = PostgresDocumentRepository(session_factory())
    return ingest_markdown_documents(repository, index)


def ingest_visual(
    *,
    pdf_path: Path,
    extraction_path: Path,
    document_key: str,
    document_name: str,
    reviewed: bool,
) -> dict[str, object]:
    if not reviewed:
        raise ValueError("図表の登録にはreview完了を示す--reviewedが必要です")
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    if not isinstance(extraction, dict):
        raise ValueError("extractionはJSON objectである必要があります")
    return ingest_visual_pdf(
        pdf_path=pdf_path,
        document_key=document_key,
        document_name=document_name,
        extraction=extraction,
        reviewed=True,
        repository=PostgresDocumentRepository(session_factory()),
        vector_index=QdrantVectorIndex(),
        asset_store=get_asset_store(),
        embeddings=get_embeddings(),
    )


def ingest_reviewed_visual_fixtures() -> dict[str, int]:
    """Publish the six reviewed, fictional visual fixtures idempotently."""

    manifest = json.loads(VISUAL_DEVELOPMENT_MANIFEST.read_text(encoding="utf-8"))
    repository = PostgresDocumentRepository(session_factory())
    index = QdrantVectorIndex()
    store = get_asset_store()
    embeddings = get_embeddings()
    ingested = 0
    for fixture in manifest["fixtures"]:
        pdf_path = BASE_DIR / fixture["document"]["path"]
        extraction = json.loads(
            (BASE_DIR / fixture["gold"]["path"]).read_text(encoding="utf-8")
        )
        extraction["source_image_sha256"] = render_pdf_page(
            pdf_path, int(extraction["page"])
        ).sha256
        ingest_visual_pdf(
            pdf_path=pdf_path,
            document_key=f"visual-demo-{fixture['fixture_id']}",
            document_name=str(extraction["title"]),
            extraction=extraction,
            reviewed=True,
            repository=repository,
            vector_index=index,
            asset_store=store,
            embeddings=embeddings,
        )
        ingested += 1
    return {"reviewed_visual_fixtures": ingested}


def extract_visual(
    *,
    pdf_path: Path,
    page_number: int,
    kind_hint: str,
    output_path: Path,
) -> dict[str, object]:
    if output_path.exists():
        raise FileExistsError(f"既存の抽出候補は上書きしません: {output_path}")
    page = render_pdf_page(pdf_path, page_number)
    candidate = extract_visual_candidate(
        page=page,
        kind_hint=kind_hint,
        provider=GeminiProvider(LLM_MODEL_NAME),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(candidate.data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "output": str(output_path),
        "provider": candidate.provider,
        "model": candidate.model,
        "prompt_version": candidate.prompt_version,
        "input_tokens": candidate.input_tokens,
        "output_tokens": candidate.output_tokens,
        "request_id": candidate.request_id,
        "review_status": "REVIEW_REQUIRED",
        "validation_errors": list(candidate.validation_errors),
        "normalized_bbox_count": candidate.normalized_bbox_count,
        "normalized_structure_count": candidate.normalized_structure_count,
    }


def reconcile() -> dict[str, object]:
    repository = PostgresDocumentRepository(session_factory())
    expected = repository.list_indexed_element_ids()
    actual = QdrantVectorIndex().list_point_ids()
    missing = sorted(str(item) for item in expected - actual)
    unexpected = sorted(str(item) for item in actual - expected)
    return {
        "postgres_indexed_elements": len(expected),
        "qdrant_points": len(actual),
        "missing_in_qdrant": missing,
        "unexpected_in_qdrant": unexpected,
        "consistent": not missing and not unexpected,
    }


def index_info() -> dict[str, object]:
    index = QdrantVectorIndex()
    points = []
    offset = None
    while True:
        batch, offset = index.client.scroll(
            collection_name=index.collection_name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(batch)
        if offset is None:
            break
    profiles = Counter(
        str((point.payload or {}).get("embedding_profile", "")) for point in points
    )
    prefixed_content = sum(
        str((point.payload or {}).get("content", "")).startswith("文書: ")
        for point in points
    )
    return {
        "collection": index.collection_name,
        "points": len(points),
        "embedding_profiles": dict(sorted(profiles.items())),
        "stored_content_with_embedding_prefix": prefixed_content,
    }


class SmokeFailure(RuntimeError):
    """A failed smoke with a report; exception text never includes provider data."""

    def __init__(self, report: dict[str, object]):
        super().__init__("smokeの必須条件を満たしませんでした。")
        self.report = report


def _smoke_exception_kind(error: Exception) -> str:
    provider_failure = (
        classify_provider_error(error) != "other"
        or type(error).__module__.startswith(("google.", "langchain_google_genai"))
        or re.search(r"\b(?:401|403|408|429|500|502|503|504)\b", str(error)) is not None
    )
    if provider_failure:
        return "PROVIDER_ERROR"
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return "FORMAT_ERROR"
    return "EXECUTION_ERROR"


def _review_response(result: object) -> dict[str, object]:
    """Selected fictional smoke evidence for a file, never a diagnostic log."""
    if not isinstance(result, Mapping):
        return {}
    references = result.get("references")
    safe_references = []
    for reference in references if isinstance(references, list) else []:
        if not isinstance(reference, Mapping):
            continue
        safe = {
            key: reference[key]
            for key in ("document_id", "document_name", "heading", "content", "source", "version_id")
            if isinstance(reference.get(key), str)
        }
        asset = reference.get("visual_asset")
        if isinstance(asset, Mapping):
            safe["visual_asset"] = {
                "mime_type": asset.get("mime_type") if isinstance(asset.get("mime_type"), str) else None,
                "page_number": asset.get("page_number") if type(asset.get("page_number")) is int else None,
                "image_loaded": isinstance(asset.get("content"), bytes) and bool(asset["content"]),
            }
        safe_references.append(safe)
    return {
        "answer": result.get("answer") if isinstance(result.get("answer"), str) else None,
        "references": safe_references,
    }


def smoke_summary(report: dict[str, object]) -> dict[str, object]:
    """Remove response bodies from the stdout/Cloud Logging summary."""
    return {
        **report,
        "results": [
            {key: value for key, value in row.items() if key != "response"}
            for row in report["results"]
        ],
    }


def smoke(
    *,
    case_ids: list[str] | None = None,
    max_cases: int = 5,
    max_attempts: int = 5,
    max_503_retries: int = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Run only fixed query checks; never migrate, ingest or rebuild an index.

    max_attempts counts complete RAG query invocations, including failed/retried
    ones. It is not a count of internal provider HTTP requests. The one-call
    candidate performs one generator and one embedding call per fixed case;
    the production path may also classify/resolve versions. Provider SDK retries
    are separate from this explicit 503 policy. No new quality score is inferred.
    """
    by_id = {case.case_id: case for case in SMOKE_CASES}
    selected_ids = list(by_id) if case_ids is None else list(case_ids)
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        raise ValueError("smoke caseは1件以上、重複なしで指定してください")
    if any(case_id not in by_id for case_id in selected_ids):
        raise ValueError("未定義のsmoke caseです")
    if not 1 <= max_cases <= len(SMOKE_CASES) or len(selected_ids) > max_cases:
        raise ValueError("選択case数を収めるmax-cases（最大5）が必要です")
    if not len(selected_ids) <= max_attempts <= len(SMOKE_CASES) * 3:
        raise ValueError("max-attemptsは選択case数以上、15以下にしてください")
    if not 0 <= max_503_retries <= 2:
        raise ValueError("max-503-retriesは0から2にしてください")

    attempts = 0
    results = []
    for case_id in selected_ids:
        case = by_id[case_id]
        attempts_before = attempts
        result = None

        def invoke():
            nonlocal attempts
            attempts += 1
            return generate_qdrant_answer(case.question)

        if attempts >= max_attempts:
            verdict = SmokeVerdict(False, "REQUEST_BUDGET_EXCEEDED", ("問い合わせ実行上限に達しました。",))
        else:
            try:
                result, _retries = run_with_503_backoff(
                    invoke,
                    sleep=sleep,
                    max_retries=min(max_503_retries, max_attempts - attempts - 1),
                )
                verdict = validate_smoke_result(result, case)
            except Exception as error:
                verdict = SmokeVerdict(False, _smoke_exception_kind(error), ("外部呼出しまたは回答処理が失敗しました。",))
        payload = result if isinstance(result, Mapping) else {}
        references = payload.get("references")
        results.append({
            "case_id": case_id,
            "status": "PASS" if verdict.passed else ("NOT_RUN" if attempts == attempts_before else "FAIL"),
            "failure_kind": verdict.failure_kind,
            "reasons": list(verdict.reasons),
            "request_id": payload.get("request_id") if isinstance(payload.get("request_id"), str) else None,
            "answer_label": payload.get("answer_label") if isinstance(payload.get("answer_label"), str) else None,
            "reference_count": len(references) if isinstance(references, list) else 0,
            "expected_labels": list(case.expected_labels),
            "matched_evidence": list(verdict.matched_evidence),
            "attempts": attempts - attempts_before,
            "provider_503_retries": max(0, attempts - attempts_before - 1),
            "semantic_review_status": "PENDING",
            "semantic_checks": list(case.semantic_checks),
            "response": _review_response(result),
        })
        # Stop on any failed required case. Remaining cases cannot be reported
        # as successful; retries never apply to poor/malformed returned answers.
        if not verdict.passed:
            break
    return {
        "schema_version": "rag-smoke-v1",
        "flow": ANSWER_GENERATION_FLOW,
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "case_ids": selected_ids,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "max_503_retries": max_503_retries,
        "budget_unit": "whole_rag_query_attempts_not_provider_http_calls",
        "structural_passed": len(results) == len(selected_ids) and all(row["status"] == "PASS" for row in results),
        "semantic_review_status": "PENDING",
        "release_ready": False,
        "not_run_case_ids": [row["case_id"] for row in results if row["status"] == "NOT_RUN"] + selected_ids[len(results):],
        "results": results,
    }


def bootstrap_cloud(
    *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, object]:
    migrate()
    ingestion = ingest()
    visual_ingestion = ingest_reviewed_visual_fixtures()
    consistency = reconcile()
    if not consistency["consistent"]:
        raise RuntimeError("PostgreSQLとQdrantのindexが一致しません")
    report = smoke(
        case_ids=["salary_day"],
        max_cases=1,
        max_attempts=3,
        max_503_retries=2,
        sleep=sleep,
    )
    if not report["structural_passed"]:
        raise SmokeFailure(report)
    checked = report["results"][0]
    return {
        "migration": "head",
        "ingestion": ingestion,
        "visual_ingestion": visual_ingestion,
        "consistency": consistency,
        "smoke": {
            "question": CLOUD_SMOKE_QUESTION,
            "request_id": checked["request_id"],
            "answer_label": checked["answer_label"],
            "references": checked["reference_count"],
            "provider_503_retries": checked["provider_503_retries"],
            "structural_passed": True,
            "semantic_review_status": "PENDING",
            "release_ready": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "migrate",
            "health",
            "ingest",
            "rebuild-qdrant",
            "reconcile",
            "index-info",
            "query",
            "smoke",
            "bootstrap-cloud",
            "ingest-visual",
            "extract-visual",
        ),
    )
    parser.add_argument("--question")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--extraction", type=Path)
    parser.add_argument("--document-key")
    parser.add_argument("--document-name")
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--kind", choices=("flowchart", "timeline", "table", "form"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", dest="case_ids", action="append", choices=[case.case_id for case in SMOKE_CASES])
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--max-503-retries", type=int, default=0)
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
        result: object = {"migration": "head"}
    elif args.command == "health":
        result = health()
    elif args.command == "ingest":
        result = ingest()
    elif args.command == "rebuild-qdrant":
        result = rebuild_qdrant()
    elif args.command == "reconcile":
        result = reconcile()
    elif args.command == "index-info":
        result = index_info()
    elif args.command == "smoke":
        try:
            # Reserve an exclusive artifact before spending any API calls.
            # The full response stays in this optional file, never in stdout.
            output_file = args.output.open("x", encoding="utf-8") if args.output else None
            try:
                report = smoke(
                    case_ids=args.case_ids,
                    max_cases=args.max_cases,
                    max_attempts=args.max_attempts,
                    max_503_retries=args.max_503_retries,
                )
                if output_file is not None:
                    json.dump(report, output_file, ensure_ascii=False, indent=2)
                    output_file.write("\n")
            finally:
                if output_file is not None:
                    output_file.close()
        except (ValueError, OSError) as error:
            print(json.dumps({"schema_version": "rag-smoke-v1", "structural_passed": False,
                              "failure_kind": "SMOKE_SETUP_FAILED", "error_type": type(error).__name__}))
            return 2
        print(json.dumps(smoke_summary(report), ensure_ascii=False, sort_keys=True))
        return 0 if report["structural_passed"] else 1
    elif args.command == "bootstrap-cloud":
        try:
            result = bootstrap_cloud()
        except SmokeFailure as error:
            print(json.dumps(smoke_summary(error.report), ensure_ascii=False, sort_keys=True))
            return 1
    elif args.command == "ingest-visual":
        required = {
            "--pdf": args.pdf,
            "--extraction": args.extraction,
            "--document-key": args.document_key,
            "--document-name": args.document_name,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.error(f"ingest-visualには{'、'.join(missing)}が必要です")
        if not args.reviewed:
            parser.error("ingest-visualにはreview完了を示す--reviewedが必要です")
        result = ingest_visual(
            pdf_path=args.pdf,
            extraction_path=args.extraction,
            document_key=args.document_key,
            document_name=args.document_name,
            reviewed=True,
        )
    elif args.command == "extract-visual":
        required = {
            "--pdf": args.pdf,
            "--kind": args.kind,
            "--output": args.output,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.error(f"extract-visualには{'、'.join(missing)}が必要です")
        result = extract_visual(
            pdf_path=args.pdf,
            page_number=args.page,
            kind_hint=args.kind,
            output_path=args.output,
        )
    else:
        if not args.question:
            parser.error("queryには--questionが必要です")
        result = generate_qdrant_answer(args.question)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
