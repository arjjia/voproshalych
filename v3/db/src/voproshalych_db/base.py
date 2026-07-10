"""Базовая модель SQLAlchemy для всех моделей базы данных.

Содержит класс Base, от которого наследуются все модели SQLAlchemy.
Использует DeclarativeBase для современного стиля SQLAlchemy 2.0.

Пример использования:
    from sqlalchemy import Column, Integer, String
    from voproshalych_db.base import Base

    class User(Base):
        __tablename__ = "users"

        id = Column(Integer, primary_key=True)
        name = Column(String(100))
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовая модель для всех SQLAlchemy моделей.

    Наследуется от DeclarativeBase (SQLAlchemy 2.0 style).
    Все модели БД должны наследоваться от этого класса.

    Атрибуты:
        metadata: Метаданные всех таблиц (создаются автоматически)
    """

    pass
