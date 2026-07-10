"""Базовый класс для парсеров источников документов."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ParsedDocument:
    """Данные распарсенного документа."""

    url: str
    title: str
    text_content: str
    source_type: str


class BaseParser(ABC):
    """Базовый абстрактный класс для парсеров источников.

    Каждый источник (Confluence, Sveden, UTMN) имеет свой парсер,
    унаследованный от этого класса.
    """

    @abstractmethod
    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        """Получить документы из источника.

        Args:
            source_url: URL страницы-источника или корень источника

        Returns:
            Список распарсенных документов
        """
        pass

    @abstractmethod
    def get_source_type(self) -> str:
        """Получить тип источника для записи в БД.

        Returns:
            Строка с типом источника (confluence, sveden, utmn)
        """
        pass
