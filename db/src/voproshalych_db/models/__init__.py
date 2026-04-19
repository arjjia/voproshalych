"""Модели базы данных Voproshalych.

Содержит все SQLAlchemy модели для таблиц базы данных.
Импортируется в migration/env.py для автогенерации миграций.

Таблицы:
- User: Пользователи платформ (Telegram, VK, MAX)
- Session: Сессии пользователей
- Message: Сообщения в чате
- QuestionAnswer: Пары вопрос-ответ
- Subscription: История подписок на рассылку
- Holiday: Праздники для рассылки
- TelemetryLog: Логи телеметрии
- AgentTrace: Трассировки агента

Пример использования:
    from voproshalych_db.models import User

    # Запрос к БД:
    user = db.query(User).filter(User.id == 1).first()
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from voproshalych_db.models.base import Base


class User(Base):
    """Модель пользователя платформы.

    Представляет пользователя одной из платформ (Telegram, VK, MAX).
    Уникальность определяется парой (platform, platform_user_id).

    Атрибуты:
        id: Уникальный идентификатор
        platform: Название платформы (telegram, vk, max)
        platform_user_id: ID пользователя на платформе
        username: Username в Telegram/VK
        first_name: Имя пользователя
        last_name: Фамилия пользователя
        is_subscribed: Флаг подписки на рассылку
        created_at: Дата создания записи
        updated_at: Дата последнего обновления
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(20), nullable=False)  # telegram, vk, max
    platform_user_id = Column(String(100), nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_subscribed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_users_platform", "platform"),
        Index("idx_users_platform_user_id", "platform", "platform_user_id"),
    )


class Session(Base):
    """Модель сессии пользователя.

    Сессия представляет отдельный диалог пользователя с ботом.
    Используется для контекста и истории сообщений.

    Атрибуты:
        id: Уникальный идентификатор
        user_id: Ссылка на пользователя
        state: Состояние диалога (START, DIALOG, WAITING_ANSWER)
        started_at: Дата начала сессии
        last_message_at: Дата последнего сообщения
    """

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    state = Column(String(20), default="START")  # START, DIALOG, WAITING_ANSWER
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_message_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="sessions")


class Message(Base):
    """Модель сообщения в чате.

    Представляет отдельное сообщение (вопрос или ответ) в сессии.

    Атрибуты:
        id: Уникальный идентификатор
        session_id: Ссылка на сессию
        role: Роль отправителя (user, assistant)
        content: Текст сообщения
        model_used: Модель LLM, которая сгенерировала ответ
        used_chunk_ids: ID чанков, использованных для ответа
        created_at: Дата создания сообщения
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    role = Column(String(10), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    model_used = Column(String(50), nullable=True)
    used_chunk_ids = Column(ARRAY(UUID), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", backref="messages")


class QuestionAnswer(Base):
    """Модель пары вопрос-ответ.

    Связывает вопрос пользователя и ответ бота.
    Позволяет анализировать качество ответов.

    Атрибуты:
        id: Уникальный идентификатор
        question_id: Ссылка на сообщение-вопрос
        answer_id: Ссылка на сообщение-ответ
        created_at: Дата создания записи
    """

    __tablename__ = "questions_answers"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    answer_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    expanded_query = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    """Модель подписки на рассылку.

    Хранит историю подписок пользователя на рассылку.

    Атрибуты:
        id: Уникальный идентификатор
        user_id: Ссылка на пользователя
        subscribed_at: Дата подписки
        unsubscribed_at: Дата отписки (NULL если активна)
    """

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref="subscriptions")


class Holiday(Base):
    """Модель праздника.

    Хранит праздники для рассылки поздравлений.

    Атрибуты:
        id: Уникальный идентификатор
        name: Название праздника
        date: Конкретная дата (для разовых)
        month: Месяц (для повторяющихся)
        day_of_month: День месяца (для повторяющихся)
        type: Тип праздника
        male_holiday: Мужской праздник
        female_holiday: Женский праздник
        template_prompt: Шаблон промпта для LLM
    """

    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    date = Column(DateTime, nullable=True)  # Конкретная дата
    month = Column(Integer, nullable=True)  # Для повторяющихся (1-12)
    day_of_month = Column(Integer, nullable=True)  # Для повторяющихся (1-31)
    type = Column(String(20), nullable=True)
    male_holiday = Column(Boolean, default=False)
    female_holiday = Column(Boolean, default=False)
    template_prompt = Column(Text, nullable=True)


class TelemetryLog(Base):
    """Модель лога телеметрии.

    Хранит логи для отладки и мониторинга.

    Атрибуты:
        id: Уникальный идентификатор
        timestamp: Время события
        level: Уровень логирования (INFO, WARNING, ERROR)
        request_id: ID запроса для трассировки
        service: Имя сервиса
        payload: JSON данные
    """

    __tablename__ = "telemetry_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    level = Column(String(10), nullable=True)  # INFO, WARNING, ERROR
    request_id = Column(UUID(as_uuid=True), nullable=True)
    service = Column(String(50), nullable=True)
    payload = Column(Text, nullable=True)  # JSON


class AgentTrace(Base):
    """Модель трассировки агента.

    Хранит шаги работы агента (для отладки LLM агентов).

    Атрибуты:
        id: Уникальный идентификатор
        request_id: ID запроса
        step: Номер шага
        phase: Фаза (reasoning, acting, evaluation)
        thought: Мысль агента
        action: Выполненное действие
        action_input: Входные данные действия
        observation: Результат действия
        created_at: Время создания записи
    """

    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(UUID(as_uuid=True), nullable=True)
    step = Column(Integer, nullable=True)
    phase = Column(String(20), nullable=True)  # reasoning, acting, evaluation
    thought = Column(Text, nullable=True)
    action = Column(String(50), nullable=True)
    action_input = Column(Text, nullable=True)
    observation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
