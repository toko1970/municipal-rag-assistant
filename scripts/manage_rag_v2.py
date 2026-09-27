"""Management commands for the PostgreSQL and Qdrant RAG v2 slice."""

from __future__ import annotations

import argparse
import json

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from config import BASE_DIR, DATABASE_URL
from src.ingestion import ingest_markdown_documents
from src.persistence.database import get_engine
from src.persistence.repositories import PostgresDocumentRepository
from src.qdrant_index import QdrantVectorIndex
from src.rag_v2 import generate_qdrant_answer


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
            "query",
        ),
    )
    parser.add_argument("--question")
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
    else:
        if not args.question:
            parser.error("queryには--questionが必要です")
        result = generate_qdrant_answer(args.question)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
