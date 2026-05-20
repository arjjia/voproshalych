"""Модуль реранкинга на основе BAAI/bge-reranker-v2-m3.

Cross-encoder модель принимает пары (query, passage) и возвращает
скор релевантности. Используется как second-stage ranking поверх
результатов LightRAG + cfgA score merge.
"""

import logging
import time
from typing import Optional

from sentence_transformers import CrossEncoder

from qa.kb.config import get_reranker_config

logger = logging.getLogger(__name__)

_reranker: Optional[CrossEncoder] = None


def get_reranker() -> CrossEncoder:
    """Получить или создать singleton реранкер.

    Returns:
        Модель CrossEncoder
    """
    global _reranker
    if _reranker is None:
        config = get_reranker_config()
        logger.info(
            "Loading reranker model: %s (max_length=%d)",
            config.reranker_model,
            config.reranker_max_length,
        )
        _reranker = CrossEncoder(
            config.reranker_model,
            max_length=config.reranker_max_length,
        )
        logger.info("Reranker model loaded")
    return _reranker


def is_reranker_enabled() -> bool:
    """Проверить, включён ли реранкер в конфигурации.

    Returns:
        True если реранкер включён
    """
    return get_reranker_config().reranker_enabled


def rerank_chunks(
    query: str,
    chunks: list[dict],
    top_k: int | None = None,
) -> list[dict]:
    """Переранжировать чанки с помощью cross-encoder.

    Формирует пары (query, chunk_content), получает скоры от модели
    и сортирует чанки по убыванию релевантности.

    При ошибке реранкера возвращает исходный порядок чанков.

    Args:
        query: Поисковый запрос
        chunks: Список чанков с ключами content, file_path, chunk_id
        top_k: Количество чанков после реранкинга.
            Если None — берётся из конфига (reranker_top_k).

    Returns:
        Отсортированный список чанков (top_k штук)
    """
    if not chunks:
        return chunks

    config = get_reranker_config()
    if top_k is None:
        top_k = config.reranker_top_k

    try:
        reranker = get_reranker()
        t0 = time.time()

        pairs = [(query, chunk.get("content", "")) for chunk in chunks]
        scores = reranker.predict(pairs)

        elapsed = time.time() - t0
        logger.info(
            "Reranker: %d pairs scored in %.3fs, top_k=%d",
            len(pairs),
            elapsed,
            top_k,
        )

        scored_chunks = list(zip(scores, chunks))
        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        return [chunk for _, chunk in scored_chunks[:top_k]]

    except Exception as exc:
        logger.warning(
            "Reranker failed, returning original order: %s", exc
        )
        return chunks[:top_k]
