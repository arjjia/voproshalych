"""Добавить уникальный constraint для идентичности пользователей платформ.

Гарантирует, что каждая пара (platform, platform_user_id) уникальна.
Это предотвращает создание дублирующихся пользователей на одной платформе.

Пример:
    # Теперь нельзя создать двух пользователей с одинаковым platform_user_id на одной платформе
    # INSERT INTO users (platform, platform_user_id) VALUES ('telegram', '123') - OK
    # INSERT INTO users (platform, platform_user_id) VALUES ('telegram', '123') - ERROR: duplicate key

Проблема которую решает:
    Ранее можно было создать несколько пользователей с одинаковым telegram_id,
    что приводило к путанице в сессиях и сообщениях.

Revision ID: 002_users_platform_unique
Revises: 001_initial
Create Date: 2026-03-21
"""

from alembic import op


revision = "002_users_platform_unique"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать уникальный constraint на пару (platform, platform_user_id).

    Создаёт ограничение уникальности с именем uq_users_platform_platform_user_id.
    """
    op.create_unique_constraint(
        "uq_users_platform_platform_user_id",
        "users",
        ["platform", "platform_user_id"],
    )


def downgrade() -> None:
    """Удалить уникальный constraint.

    Внимание: после удаления возможны дубликаты!
    """
    op.drop_constraint(
        "uq_users_platform_platform_user_id",
        "users",
        type_="unique",
    )
