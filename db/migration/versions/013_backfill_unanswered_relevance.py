"""Сохранить ревизию для исторических данных без изменения записей.

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
    pass


def downgrade() -> None:
    pass
