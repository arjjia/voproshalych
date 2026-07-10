"""Конфигурация окружения Alembic для миграций базы данных.

Содержит настройки Alembic для выполнения миграций в онлайн и офлайн режимах.
Загружает модели SQLAlchemy для автогенерации миграций.

Режимы работы:
- Offline: миграции выполняются без подключения к БД (только SQL скрипты)
- Online: миграции выполняются через подключение к БД

Основные функции:
- run_migrations_offline(): Офлайн режим
- run_migrations_online(): Онлайн режим (используется по умолчанию)

Пример выполнения миграций:
    alembic upgrade head        # Применить все миграции
    alembic downgrade -1        # Откатить последнюю
    alembic current            # Показать текущую версию
    alembic history            # Показать историю миграций
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from voproshalych_db.models.base import Base
from voproshalych_db.models import *  # noqa: F401, F403
from voproshalych_db import DATABASE_URL

# Import all models to register them with Base
from voproshalych_db.models import *  # noqa: F401, F403

# this is the Alembic Config object
config = context.config

# Set sqlalchemy.url from our config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Выполнить миграции в офлайн режиме.

    В офлайн режиме Alembic генерирует SQL скрипты,
    но не выполняет их. Используется для:
    - Предварительного просмотра изменений
    - Ручного выполнения миграций
    - Работы без подключения к БД

    Args:
        None

    Note:
        Офлайн режим активируется флагом --sql:
            alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Выполнить миграции в онлайн режиме.

    В онлайн режиме Alembic напрямую выполняет миграции
    в базе данных через SQLAlchemy движок.
    Это основной режим работы при развёртывании.

    Процесс:
    1. Создать подключение к БД
    2. Настроить контекст Alembic
    3. Выполнить все pending миграции
    4. Записать версию в alembic_version

    Args:
        None

    Note:
        Используется по умолчанию при команде:
            alembic upgrade head
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
