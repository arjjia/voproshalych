"""Убрать ограничение длины поля source_url в chunks.

Revision ID: 006_chunks_source_url_length
Revises: 005_chunks_title_length
Create Date: 2026-04-13

"""

from alembic import op

revision = "006_chunks_source_url_length"
down_revision = "005_chunks_title_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chunks ALTER COLUMN source_url TYPE TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE chunks ALTER COLUMN source_url TYPE VARCHAR(500);")