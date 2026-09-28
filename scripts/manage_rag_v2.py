"""Management commands for the PostgreSQL and Qdrant RAG v2 slice."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from config import BASE_DIR, DATABASE_URL, VISUAL_ASSET_DIR
from src.asset_store import LocalAssetStore
from src.embeddings import get_embeddings
from src.ingestion import ingest_markdown_documents
from src.persistence.database import get_engine
from src.persistence.repositories import PostgresDocumentRepository
from src.qdrant_index import QdrantVectorIndex
from src.rag_v2 import generate_qdrant_answer
from src.visual_ingestion import ingest_visual_pdf


CLOUD_SMOKE_QUESTION = "給与支給日はいつですか？"


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
        asset_store=LocalAssetStore(VISUAL_ASSET_DIR),
        embeddings=get_embeddings(),
    )


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


def bootstrap_cloud() -> dict[str, object]:
    migrate()
    ingestion = ingest()
    consistency = reconcile()
    if not consistency["consistent"]:
        raise RuntimeError("PostgreSQLとQdrantのindexが一致しません")
    answer = generate_qdrant_answer(CLOUD_SMOKE_QUESTION)
    return {
        "migration": "head",
        "ingestion": ingestion,
        "consistency": consistency,
        "smoke": {
            "question": CLOUD_SMOKE_QUESTION,
            "request_id": answer["request_id"],
            "answer_label": answer["answer_label"],
            "references": len(answer["references"]),
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
        ),
    )
    parser.add_argument("--question")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--extraction", type=Path)
    parser.add_argument("--document-key")
    parser.add_argument("--document-name")
    parser.add_argument("--reviewed", action="store_true")
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
    else:
        if not args.question:
            parser.error("queryには--questionが必要です")
        result = generate_qdrant_answer(args.question)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
