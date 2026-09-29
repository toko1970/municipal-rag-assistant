"""Management commands for the PostgreSQL and Qdrant RAG v2 slice."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Callable, TypeVar

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from config import BASE_DIR, DATABASE_URL, LLM_MODEL_NAME
from src.asset_backend import get_asset_store
from src.embeddings import get_embeddings
from src.ingestion import ingest_markdown_documents
from src.llm_provider import GeminiProvider
from src.persistence.database import get_engine
from src.persistence.repositories import PostgresDocumentRepository
from src.qdrant_index import QdrantVectorIndex
from src.rag_v2 import generate_qdrant_answer
from src.visual_ingestion import ingest_visual_pdf
from src.visual_extractor import extract_visual_candidate
from src.visual_ingestion import render_pdf_page


CLOUD_SMOKE_QUESTION = "給与支給日はいつですか？"
SMOKE_MAX_503_RETRIES = 2
SMOKE_BACKOFF_INITIAL_SECONDS = 5.1
SMOKE_BACKOFF_MAX_SECONDS = 10.2
VISUAL_DEVELOPMENT_MANIFEST = (
    BASE_DIR / "eval/visual_fixtures/manifests/development_manifest.json"
)

T = TypeVar("T")


def _is_retryable_provider_503(error: Exception) -> bool:
    text = str(error).upper()
    return "503" in text and ("UNAVAILABLE" in text or "HIGH DEMAND" in text)


def run_with_503_backoff(
    operation: Callable[[], T],
    *,
    sleep: Callable[[float], None] = time.sleep,
    max_retries: int = SMOKE_MAX_503_RETRIES,
    backoff_initial_seconds: float = SMOKE_BACKOFF_INITIAL_SECONDS,
    backoff_max_seconds: float = SMOKE_BACKOFF_MAX_SECONDS,
) -> tuple[T, int]:
    """Retry only transient Gemini 503 errors with a bounded exponential delay."""

    for retry_count in range(max_retries + 1):
        try:
            return operation(), retry_count
        except Exception as error:
            if retry_count >= max_retries or not _is_retryable_provider_503(error):
                raise
            delay = min(
                backoff_initial_seconds * (2**retry_count),
                backoff_max_seconds,
            )
            print(
                json.dumps(
                    {
                        "event": "provider_503_retry",
                        "retry": retry_count + 1,
                        "max_retries": max_retries,
                        "backoff_seconds": delay,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            sleep(delay)
    raise AssertionError("unreachable")


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


def bootstrap_cloud(
    *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, object]:
    migrate()
    ingestion = ingest()
    visual_ingestion = ingest_reviewed_visual_fixtures()
    consistency = reconcile()
    if not consistency["consistent"]:
        raise RuntimeError("PostgreSQLとQdrantのindexが一致しません")
    answer, provider_503_retries = run_with_503_backoff(
        lambda: generate_qdrant_answer(CLOUD_SMOKE_QUESTION),
        sleep=sleep,
    )
    return {
        "migration": "head",
        "ingestion": ingestion,
        "visual_ingestion": visual_ingestion,
        "consistency": consistency,
        "smoke": {
            "question": CLOUD_SMOKE_QUESTION,
            "request_id": answer["request_id"],
            "answer_label": answer["answer_label"],
            "references": len(answer["references"]),
            "provider_503_retries": provider_503_retries,
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
    elif args.command == "bootstrap-cloud":
        result = bootstrap_cloud()
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
