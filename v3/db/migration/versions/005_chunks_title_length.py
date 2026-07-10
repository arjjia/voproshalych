"""Убрать ограничение длины поля title в chunks.

Revision ID: 005_chunks_title_length
Revises: 004_add_vector_column
Create Date: 2026-04-13

"""

from alembic import op

revision = "005_chunks_title_length"
down_revision = "004_add_vector_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chunks ALTER COLUMN title TYPE TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE chunks ALTER COLUMN title TYPE VARCHAR(500);")