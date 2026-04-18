"""Векторный поиск в Базе Знаний через LightRAG.

Осуществляет семантический поиск по документам используя LightRAG
vector storage с косинусным сходством.
"""

import logging
from typing import Optional

from .config import get_kb_config

logger = logging.getLogger(__name__)


async def search_chunks(
    query: str,
    embedding: list[float],
    top_k: int = 5,
    max_similarity: float | None = None,
) -> list[dict]:
    """Найти похожие документы через LightRAG vector storage.

    Использует LightRAG для поиска по векторам с косинусным сходством.

    Args:
        query: Текст запроса пользователя (для логирования)
        embedding: Вектор эмбеддинга запроса
        top_k: Количество возвращаемых результатов
        max_similarity: Порог косинусного сходства (не используется,
                        оставлен для совместимости API)

    Returns:
        Список документов с текстом, источником и оценкой похожести
    """
    from ..main import get_lightrag, is_lightrag_ready

    if not is_lightrag_ready():
        raise RuntimeError("LightRAG not initialized")

    if max_similarity is None:
        max_similarity = get_kb_config().search_similarity_threshold

    rag = get_lightrag()

    try:
        results = await rag.asearch(
            query=query,
            top_k=top_k,
        )

        chunks = []
        for i, item in enumerate(results):
            text = item.get("text", "")
            title = item.get("title", item.get("name", "Untitled"))
            source_url = item.get("url", item.get("file_path", ""))

            chunks.append(
                {
                    "id": str(i),
                    "text": text,
                    "title": title,
                    "source_url": source_url,
                    "similarity": 1.0 - (item.get("distance", 0.0)),
                }
            )

    except Exception as e:
        logger.error(f"LightRAG search failed: {e}")
        raise

    logger.info(
        "Found %d documents for query: %s...",
        len(chunks),
        query[:50],
    )
    return chunks


def build_context_from_chunks(chunks: list[dict]) -> str:
    """Построить контекст из чанков для LLM.

    Формирует текстовый контекст в формате:
    --- Документ N ---
    Источник: ...
    Название: ...
    Содержание: ...

    Args:
        chunks: Список чанков с текстом и метаданными

    Returns:
        Текст контекста для использования в промпте LLM
    """
    if not chunks:
        return ""

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_url", "Unknown")
        title = chunk.get("title", "Untitled")
        text = chunk["text"]

        context_parts.append(
            f"--- Документ {i} ---\n"
            f"Источник: {source}\n"
            f"Название: {title}\n"
            f"Содержание: {text}\n"
        )

    return "\n\n".join(context_parts)