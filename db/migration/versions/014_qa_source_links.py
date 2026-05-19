"""Сохранять ссылки на источники ответа.

Revision ID: 014_qa_source_links
Revises: 013_unanswered_backfill
Create Date: 2026-05-19

"""

from alembic import op

revision = "014_qa_source_links"
down_revision = "013_unanswered_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "ADD COLUMN IF NOT EXISTS source_links TEXT;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "DROP COLUMN IF EXISTS source_links;"
    )
