"""Добавить историю сохраненных задач канбана.

Revision ID: 017_task_reports
Revises: 016_done_tasks_document_added
Create Date: 2026-05-19

"""

from alembic import op

revision = "017_task_reports"
down_revision = "016_done_tasks_document_added"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_task_reports (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            tasks_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    op.execute(
        """
        ALTER TABLE admin_tasks
        ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS report_id INTEGER REFERENCES admin_task_reports(id)
            ON DELETE SET NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_tasks_archived_at
        ON admin_tasks(archived_at);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_task_report_items (
            id SERIAL PRIMARY KEY,
            report_id INTEGER NOT NULL REFERENCES admin_task_reports(id) ON DELETE CASCADE,
            task_id INTEGER REFERENCES admin_tasks(id) ON DELETE SET NULL,
            question_id INTEGER NOT NULL,
            answer_id INTEGER,
            question TEXT NOT NULL,
            answer TEXT,
            platform VARCHAR(32),
            platform_user_id VARCHAR(255),
            username VARCHAR(255),
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            asked_at TIMESTAMPTZ NOT NULL,
            model_used VARCHAR(255),
            sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_task_report_items_report_id
        ON admin_task_report_items(report_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_task_report_items;")
    op.execute(
        """
        ALTER TABLE admin_tasks
        DROP COLUMN IF EXISTS report_id,
        DROP COLUMN IF EXISTS archived_at;
        """
    )
    op.execute("DROP TABLE IF EXISTS admin_task_reports;")
