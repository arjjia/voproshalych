"""Добавить колонку relevance_type в questions_answers.

Revision ID: 011_relevance_type
Revises: 010_dialog_context_fields
Create Date: 2026-05-11

"""

from alembic import op

revision = "011_relevance_type"
down_revision = "010_dialog_context_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "ADD COLUMN IF NOT EXISTS relevance_type VARCHAR(1);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "DROP COLUMN IF EXISTS relevance_type;"
    )
