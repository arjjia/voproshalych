"""Парсеры источников документов для Базы Знаний."""

from .base import BaseParser, ParsedDocument
from .confluence import ConfluenceParser
from .confluence_study import ConfluenceStudyParser
from .sveden import SvedenParser
from .utmn import UtmnParser
from .web import WebPageParser

__all__ = [
    "BaseParser",
    "ParsedDocument",
    "ConfluenceParser",
    "ConfluenceStudyParser",
    "SvedenParser",
    "UtmnParser",
    "WebPageParser",
]
