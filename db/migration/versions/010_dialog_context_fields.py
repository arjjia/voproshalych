"""Добавить колонки normalized_query, question_type в messages и normalized_context в questions_answers.

Revision ID: 010_dialog_context_fields
Revises: 009_messages_feedback
Create Date: 2026-05-11

"""

from alembic import op

revision = "010_dialog_context_fields"
down_revision = "009_messages_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "ADD COLUMN IF NOT EXISTS normalized_query TEXT;"
    )
    op.execute(
        "ALTER TABLE messages "
        "ADD COLUMN IF NOT EXISTS question_type INTEGER;"
    )
    op.execute(
        "ALTER TABLE questions_answers "
        "ADD COLUMN IF NOT EXISTS normalized_context TEXT;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "DROP COLUMN IF EXISTS normalized_query;"
    )
    op.execute(
        "ALTER TABLE messages "
        "DROP COLUMN IF EXISTS question_type;"
    )
    op.execute(
        "ALTER TABLE questions_answers "
        "DROP COLUMN IF EXISTS normalized_context;"
    )
