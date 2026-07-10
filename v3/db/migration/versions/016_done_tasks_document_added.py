"""Отметить выполненные задачи как документ добавлен.

Revision ID: 016_done_tasks_document_added
Revises: 015_admin_tasks
Create Date: 2026-05-19

"""

from alembic import op

revision = "016_done_tasks_document_added"
down_revision = "015_admin_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE questions_answers qa
        SET admin_status_override = 'document_added'
        FROM admin_tasks t
        WHERE t.status = 'done'
          AND qa.question_id = t.question_id
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE questions_answers qa
        SET admin_status_override = NULL
        FROM admin_tasks t
        WHERE t.status = 'done'
          AND qa.question_id = t.question_id
          AND qa.admin_status_override = 'document_added'
        """
    )
