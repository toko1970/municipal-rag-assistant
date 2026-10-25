"""Compatibility exports for the PostgreSQL persistence adapters."""

from src.persistence.document_repository import (
    PostgresDocumentRepository as PostgresDocumentRepository,
)
from src.persistence.event_logger import PostgresEventLogger as PostgresEventLogger
