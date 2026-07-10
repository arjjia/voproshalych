"""Добавить колонку relevant_sources в questions_answers.

Revision ID: 012_relevant_sources
Revises: 011_relevance_type
Create Date: 2026-05-12

"""

from alembic import op

revision = "012_relevant_sources"
down_revision = "011_relevance_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "ADD COLUMN IF NOT EXISTS relevant_sources TEXT;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "DROP COLUMN IF EXISTS relevant_sources;"
    )
