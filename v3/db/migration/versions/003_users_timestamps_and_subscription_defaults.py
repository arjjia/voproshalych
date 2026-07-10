"""Нормализует timestamps пользователей и значения по умолчанию для подписки.

Выполняет нормализацию таблицы users:
1. Заполняет NULL значения в is_subscribed значением false
2. Заполняет NULL значения в created_at текущим временем
3. Заполняет NULL значения в updated_at текущим временем
4. Делает колонки NOT NULL

Проблема которую решает:
    - При создании миграции 001_initial колонки были nullable=True
    - Это создавало проблемы с NOT NULL constraint в приложении
    - Теперь все обязательные поля имеют значения

Пример проблемы:
    # До миграции:
    # users.is_subscribed = NULL  (непонятно: подписан или нет)
    # users.created_at = NULL    (неизвестно когда создан)

    # После миграции:
    # users.is_subscribed = false (явно не подписан)
    # users.created_at = 2026-03-21 12:00:00 (известно время создания)

Revision ID: 003_users_ts_defaults
Revises: 002_users_platform_unique
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa


revision = "003_users_ts_defaults"
down_revision = "002_users_platform_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Нормализовать значения и сделать колонки NOT NULL.

    Этапы:
    1. UPDATE - заполнить NULL значениями
    2. ALTER - изменить nullable=False
    """
    # Заполняем NULL значения перед изменением на NOT NULL
    op.execute("UPDATE users SET is_subscribed = false WHERE is_subscribed IS NULL")
    op.execute("UPDATE users SET created_at = now() WHERE created_at IS NULL")
    op.execute("UPDATE users SET updated_at = now() WHERE updated_at IS NULL")

    # Меняем nullable на NOT NULL
    op.alter_column(
        "users",
        "is_subscribed",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    """Разрешить NULL значения в колонках.

    Внимание: после отката поля могут содержать NULL.
    """
    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "users",
        "is_subscribed",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=sa.text("false"),
    )
