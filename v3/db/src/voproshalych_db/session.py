"""Модуль управления подключением к базе данных.

Содержит конфигурацию подключения к PostgreSQL, создание движка (engine)
и фабрику сессий для работы с базой данных через SQLAlchemy.

Пример использования:
    from voproshalych_db.session import get_db, SessionLocal

    # В FastAPI Depends():
    @app.get("/users")
    def get_users(db: Session = Depends(get_db)):
        return db.query(User).all()
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv


def _find_env_file() -> Path | None:
    """Найти .env файл в директориях выше текущей.

    Ищет файл .env в директориях:
    - Текущая директория
    - Родительская
    - И так далее (до 5 уровней вложенности)

    Returns:
        Path | None: Путь к .env файлу или None, если не найден.
    """
    current = Path(__file__).parent
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            return env_path
        current = current.parent
    return None


if env_file := _find_env_file():
    load_dotenv(env_file)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "voproshalych")
POSTGRES_USER = os.getenv("POSTGRES_USER", "voproshalych")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "voproshalych")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Получить сессию базы данных.

    Generator-функция для использования в FastAPI Depends().
    Сессия автоматически закрывается после использования.

    Yields:
        Session: Сессия SQLAlchemy для выполнения запросов к БД.

    Пример использования:
        from fastapi import Depends

        @app.get("/items/{item_id}")
        def get_item(item_id: int, db: Session = Depends(get_db)):
            return db.query(Item).get(item_id)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
