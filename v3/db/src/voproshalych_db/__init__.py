"""Пакет базы данных Voproshalych.

Содержит основные компоненты для работы с базой данных:
- Base: Базовый класс для SQLAlchemy моделей
- get_db: Generator для получения сессии БД (FastAPI Depends)
- SessionLocal: Фабрика сессий SQLAlchemy
- engine: Движок подключения к БД
- DATABASE_URL: Строка подключения к PostgreSQL

Быстрый старт:
    from voproshalych_db import get_db, Base
    from voproshalych_db.models import User

    # В FastAPI:
    @app.get("/users")
    def get_users(db = Depends(get_db)):
        return db.query(User).all()
"""

from .base import Base
from .session import get_db, SessionLocal, engine, DATABASE_URL

__all__ = [
    "Base",
    "get_db",
    "SessionLocal",
    "engine",
    "DATABASE_URL",
]
