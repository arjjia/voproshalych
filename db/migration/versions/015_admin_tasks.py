"""Добавить админские задачи и override статуса Q&A.

Revision ID: 015_admin_tasks
Revises: 014_qa_source_links
Create Date: 2026-05-19

"""

from alembic import op

revision = "015_admin_tasks"
down_revision = "014_qa_source_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE questions_answers "
        "ADD COLUMN IF NOT EXISTS admin_status_override VARCHAR(32);"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS admin_tasks ("
        "id SERIAL PRIMARY KEY, "
        "question_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE, "
        "answer_id INTEGER REFERENCES messages(id) ON DELETE SET NULL, "
        "status VARCHAR(32) NOT NULL DEFAULT 'added', "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "UNIQUE(question_id)"
        ");"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_tasks_status "
        "ON admin_tasks(status);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_tasks;")
    op.execute(
        "ALTER TABLE questions_answers "
        "DROP COLUMN IF EXISTS admin_status_override;"
    )
