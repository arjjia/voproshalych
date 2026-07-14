"""Парсеры источников документов для Базы Знаний."""

from .base import BaseParser, ParsedDocument
from .confluence_help import ConfluenceHelpParser
from .confluence_study import ConfluenceStudyParser
from .utmn_news import UtmnNewsParser
from .web import WebPageParser

__all__ = [
    "BaseParser",
    "ParsedDocument",
    "ConfluenceHelpParser",
    "ConfluenceStudyParser",
    "UtmnNewsParser",
    "WebPageParser",
]
