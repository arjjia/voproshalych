"""Базовая модель SQLAlchemy для модуля моделей.

Дублирует базовый класс Base для обратной совместимости.
Рекомендуется использовать voproshalych_db.base.Base напрямую.

Пример использования:
    from voproshalych_db.models.base import Base

    class Item(Base):
        __tablename__ = "items"
        ...
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовая модель для SQLAlchemy моделей.

    Алиас для voproshalych_db.base.Base.
    Используется для определения таблиц базы данных.
    """

    pass
