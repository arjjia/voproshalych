"""Добавить expanded_query и keywords в questions_answers.

Хранение расширенного запроса (после LLM-предобработки) и извлечённых
ключевых слов (high_level, low_level) для аналитики и отладки.

Revision ID: 008_qa_expanded_query_keywords
Revises: 007_drop_chunks_embeddings
Create Date: 2026-04-19

"""

from alembic import op

revision = "008_qa_expanded_query_keywords"
down_revision = "007_drop_chunks_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "ADD COLUMN IF NOT EXISTS expanded_query TEXT, "
        "ADD COLUMN IF NOT EXISTS keywords TEXT;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "DROP COLUMN IF EXISTS keywords, "
        "DROP COLUMN IF EXISTS expanded_query;"
    )
