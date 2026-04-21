"""Добавить колонку feedback в messages.

Хранение оценки пользователя (like/dislike) для ответов бота.
Значения: NULL (не оценено), 'like', 'dislike'.

Revision ID: 009_messages_feedback
Revises: 008_qa_expanded_query_keywords
Create Date: 2026-04-21

"""

from alembic import op

revision = "009_messages_feedback"
down_revision = "008_qa_expanded_query_keywords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "ADD COLUMN IF NOT EXISTS feedback VARCHAR(10);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "DROP COLUMN IF EXISTS feedback;"
    )
