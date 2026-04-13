"""Разбиение текста на чанки для Базы Знаний."""

import logging
from dataclasses import dataclass
from typing import Generator

from langchain_text_splitters import RecursiveCharacterTextSplitter

from qa.kb.config import get_kb_config

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Чанк текста из документа."""

    text: str
    source_url: str
    title: str
    chunk_index: int


class TextChunker:
    """Разбиение текста на перекрывающиеся чанки по предложениям."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
    ):
        """Инициализировать чанкер.

        Args:
            chunk_size: Максимальный размер чанка в символах
            chunk_overlap: Перекрытие между чанками в символах
            min_chunk_size: Минимальный размер чанка для сохранения
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n\n", "\n\n", "\n", ". "],
            length_function=len,
            keep_separator=True,
        )

    def chunk_text(
        self,
        text: str,
        source_url: str,
        title: str = "",
    ) -> Generator[Chunk, None, None]:
        """Разбить текст на перекрывающиеся чанки.

        Использует RecursiveCharacterTextSplitter для разбиения
        по предложениям с ограничением максимального размера чанка.

        Args:
            text: Текст для разбиения
            source_url: URL источника документа
            title: Название документа

        Yields:
            Объекты Chunk
        """
        text = text.strip()
        if not text:
            logger.warning(f"Empty text for {source_url}")
            return

        chunks = self._splitter.split_text(text)

        for i, chunk_text in enumerate(chunks):
            if len(chunk_text) >= self.min_chunk_size:
                yield Chunk(
                    text=chunk_text,
                    source_url=source_url,
                    title=title or source_url,
                    chunk_index=i,
                )

        logger.info(f"Created {len(chunks)} chunks from {source_url}")


def get_chunker() -> TextChunker:
    """Получить чанкер с настройками из конфига.

    Returns:
        TextChunker с параметрами из KBConfig
    """
    config = get_kb_config()
    return TextChunker(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        min_chunk_size=config.min_chunk_size,
    )