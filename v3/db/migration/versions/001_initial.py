"""Начальная миграция: создание всех таблиц базы данных.

Создаёт все таблицы для приложения Voproshalych:
- users: Пользователи платформ (Telegram, VK, MAX)
- sessions: Сессии пользователей
- messages: Сообщения в чате
- questions_answers: Пары вопрос-ответ
- chunks: Чанки базы знаний
- embeddings: Векторные представления чанков
- subscriptions: История подписок на рассылку
- holidays: Праздники для рассылки
- telemetry_logs: Логи телеметрии
- agent_traces: Трассировки агента

Также создаёт индексы для часто используемых полей:
- idx_users_platform
- idx_users_platform_user_id
- idx_sessions_user_id
- idx_messages_session
- idx_chunks_source
- idx_holidays_date
- idx_holidays_month
- idx_telemetry_timestamp
- idx_agent_traces_request

Revision ID: 001_initial
Revises: (нет предыдущей миграции)
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создать все таблицы и индексы базы данных.

    Создаёт 10 таблиц с первичными ключами, внешними ключами,
    индексами и значениями по умолчанию для временных меток.
    """
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_user_id", sa.String(100), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("is_subscribed", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_users_platform", "users", ["platform"])
    op.create_index(
        "idx_users_platform_user_id", "users", ["platform", "platform_user_id"]
    )

    # Sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=True, server_default="START"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])

    # Messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("used_chunk_ids", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_session", "messages", ["session_id"])

    # Questions_answers table
    op.create_table(
        "questions_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["question_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["answer_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Chunks table
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chunks_source", "chunks", ["source_type"])

    # Embeddings table with pgvector
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "embedding", sa.Text(), nullable=False
        ),  # Store as JSON for compatibility
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "subscribed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Holidays table
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("date", sa.DateTime, nullable=True),
        sa.Column("month", sa.Integer, nullable=True),
        sa.Column("day_of_month", sa.Integer, nullable=True),
        sa.Column("type", sa.String(20), nullable=True),
        sa.Column("male_holiday", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column(
            "female_holiday", sa.Boolean(), nullable=True, server_default="false"
        ),
        sa.Column("template_prompt", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_holidays_date", "holidays", ["date"])
    op.create_index("idx_holidays_month", "holidays", ["month", "day_of_month"])

    # Telemetry_logs table
    op.create_table(
        "telemetry_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("level", sa.String(10), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service", sa.String(50), nullable=True),
        sa.Column("payload", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_telemetry_timestamp", "telemetry_logs", ["timestamp"])

    # Agent_traces table
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("step", sa.Integer, nullable=True),
        sa.Column("phase", sa.String(20), nullable=True),
        sa.Column("thought", sa.Text, nullable=True),
        sa.Column("action", sa.String(50), nullable=True),
        sa.Column("action_input", sa.Text, nullable=True),
        sa.Column("observation", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_traces_request", "agent_traces", ["request_id"])


def downgrade() -> None:
    """Удалить все таблицы базы данных.

    Удаляет таблицы в обратном порядке (с учётом зависимостей).
    Внимание: все данные будут потеряны!
    """
    op.drop_table("agent_traces")
    op.drop_table("telemetry_logs")
    op.drop_table("holidays")
    op.drop_table("subscriptions")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("questions_answers")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("users")


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_user_id", sa.String(100), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("is_subscribed", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_users_platform", "users", ["platform"])
    op.create_index(
        "idx_users_platform_user_id", "users", ["platform", "platform_user_id"]
    )

    # Sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=True, server_default="START"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])

    # Messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("used_chunk_ids", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_session", "messages", ["session_id"])

    # Questions_answers table
    op.create_table(
        "questions_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["question_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["answer_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Chunks table
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chunks_source", "chunks", ["source_type"])

    # Embeddings table with pgvector
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "embedding", sa.Text(), nullable=False
        ),  # Store as JSON for compatibility
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "subscribed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Holidays table
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("date", sa.DateTime, nullable=True),
        sa.Column("month", sa.Integer, nullable=True),
        sa.Column("day_of_month", sa.Integer, nullable=True),
        sa.Column("type", sa.String(20), nullable=True),
        sa.Column("male_holiday", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column(
            "female_holiday", sa.Boolean(), nullable=True, server_default="false"
        ),
        sa.Column("template_prompt", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_holidays_date", "holidays", ["date"])
    op.create_index("idx_holidays_month", "holidays", ["month", "day_of_month"])

    # Telemetry_logs table
    op.create_table(
        "telemetry_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("level", sa.String(10), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service", sa.String(50), nullable=True),
        sa.Column("payload", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_telemetry_timestamp", "telemetry_logs", ["timestamp"])

    # Agent_traces table
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("step", sa.Integer, nullable=True),
        sa.Column("phase", sa.String(20), nullable=True),
        sa.Column("thought", sa.Text, nullable=True),
        sa.Column("action", sa.String(50), nullable=True),
        sa.Column("action_input", sa.Text, nullable=True),
        sa.Column("observation", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_traces_request", "agent_traces", ["request_id"])


def downgrade() -> None:
    op.drop_table("agent_traces")
    op.drop_table("telemetry_logs")
    op.drop_table("holidays")
    op.drop_table("subscriptions")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("questions_answers")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("users")
