"""Укрепить инварианты админ-панели.

Revision ID: 018_admin_panel_hardening
Revises: 017_task_reports
Create Date: 2026-05-19

"""

from alembic import op

revision = "018_admin_panel_hardening"
down_revision = "017_task_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM admin_tasks t
        USING questions_answers qa
        WHERE t.question_id = qa.question_id
          AND t.archived_at IS NULL
          AND qa.admin_status_override = 'answered';
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION try_parse_jsonb(value text)
        RETURNS jsonb
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN value::jsonb;
        EXCEPTION WHEN others THEN
            RETURN '[]'::jsonb;
        END;
        $$;
        """
    )
    op.execute(
        """
        ALTER TABLE questions_answers
        ALTER COLUMN source_links TYPE JSONB
        USING CASE
            WHEN source_links IS NULL OR source_links::text = '' THEN '[]'::jsonb
            ELSE try_parse_jsonb(source_links::text)
        END;
        """
    )
    op.execute(
        """
        ALTER TABLE questions_answers
        ALTER COLUMN source_links SET DEFAULT '[]'::jsonb;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS try_parse_jsonb(text);")
    op.execute(
        """
        ALTER TABLE admin_task_report_items
        ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS restored_task_id INTEGER REFERENCES admin_tasks(id)
            ON DELETE SET NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE admin_task_report_items
        DROP COLUMN IF EXISTS restored_task_id,
        DROP COLUMN IF EXISTS restored_at;
        """
    )
    op.execute(
        """
        ALTER TABLE questions_answers
        ALTER COLUMN source_links DROP DEFAULT;
        """
    )
    op.execute(
        """
        ALTER TABLE questions_answers
        ALTER COLUMN source_links TYPE TEXT
        USING source_links::text;
        """
    )
