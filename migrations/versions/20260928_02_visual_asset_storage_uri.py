"""Rename the visual asset locator for local and GCS backends."""

from collections.abc import Sequence

from alembic import op


revision: str = "20260928_02"
down_revision: str | None = "20260927_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("visual_assets", "local_path", new_column_name="storage_uri")


def downgrade() -> None:
    op.alter_column("visual_assets", "storage_uri", new_column_name="local_path")
