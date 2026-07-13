"""Генерация эмбеддингов локальной моделью deepvk/USER-bge-m3.

Перенос подхода из v2 (qa-service/src/qa/kb/embedding.py): модель
SentenceTransformer загружается один раз (singleton) и переиспользуется.
Размерность — 1024 (соответствует pgvector `vector(1024)` в kb_embeddings).

Синхронные вызовы SentenceTransformer (CPU-bound) выполняются в пуле потоков
через ``asyncio.to_thread``, чтобы не блокировать event loop сервиса.
"""

import asyncio
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

from kb.config import settings as default_settings

logger = logging.getLogger(__name__)

_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    """Вернуть singleton-инстанс модели (потокобезопасно через GIL)."""
    global _model
    if _model is None:
        model_name = default_settings.embedding_model
        logger.info("Loading embedding model: %s", model_name)
        _model = SentenceTransformer(model_name)
        logger.info(
            "Embedding model loaded, dim=%s",
            _model.get_sentence_embedding_dimension(),
        )
    return _model


def _encode_sync(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(
        texts, normalize_embeddings=True, show_progress_bar=False
    )
    return embeddings.tolist()


async def get_embedding(text: str, settings=None) -> list[float]:
    """Сгенерировать эмбеддинг для одного текста.

    Args:
        text: текст для эмбеддинга.
        settings: (не используется) оставлено для совместимости сигнатуры.

    Returns:
        Вектор эмбеддинга как список float.
    """
    result = await asyncio.to_thread(_encode_sync, [text])
    return result[0]


async def get_embeddings_batch(
    texts: list[str], settings=None
) -> list[list[float]]:
    """Сгенерировать эмбеддинги для списка текстов.

    Args:
        texts: список текстов.
        settings: (не используется) оставлено для совместимости сигнатуры.

    Returns:
        Список векторов эмбеддингов.
    """
    return await asyncio.to_thread(_encode_sync, list(texts))
