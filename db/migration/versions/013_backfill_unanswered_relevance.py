"""Заполнить relevance_type для исторических неотвеченных ответов.

Revision ID: 013_unanswered_backfill
Revises: 012_relevant_sources
Create Date: 2026-05-19

"""

from alembic import op

revision = "013_unanswered_backfill"
down_revision = "012_relevant_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE questions_answers qa
        SET relevance_type = 'b'
        FROM messages am
        WHERE qa.answer_id = am.id
          AND qa.relevance_type IS NULL
          AND am.content ILIKE '%нет информации из официальной базы знаний%';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE questions_answers qa
        SET relevance_type = NULL
        FROM messages am
        WHERE qa.answer_id = am.id
          AND qa.relevance_type = 'b'
          AND am.content ILIKE '%нет информации из официальной базы знаний%';
        """
    )
