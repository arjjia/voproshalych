"""Cross-encoder reranker для переранжирования результатов поиска."""

import logging
import os
from functools import lru_cache
from typing import List, Optional

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "DiTy/cross-encoder-russian-msmarco"


@lru_cache(maxsize=1)
def _load_reranker() -> Optional[CrossEncoder]:
    model_name = os.getenv("RERANKER_MODEL", DEFAULT_RERANKER_MODEL)
    try:
        logger.info("Loading reranker model: %s", model_name)
        model = CrossEncoder(model_name, max_length=512)
        logger.info("Reranker model loaded: %s", model_name)
        return model
    except Exception as e:
        logger.error("Failed to load reranker model '%s': %s", model_name, e)
        return None


def get_reranker() -> Optional[CrossEncoder]:
    if os.getenv("RERANKER_ENABLED", "false").lower() != "true":
        return None
    return _load_reranker()


def rerank_chunks(
    query: str,
    chunks: List[dict],
    top_k: int = 8,
    max_content_len: int = 400,
) -> List[dict]:
    """Переранжировать чанки с помощью cross-encoder.

    Args:
        query: Поисковый запрос.
        chunks: Список чанков с полем 'content'.
        top_k: Сколько чанков вернуть после переранжирования.
        max_content_len: Максимальная длина текста чанка для скоринга.

    Returns:
        Переранжированный список чанков (top_k).
    """
    model = get_reranker()
    if not model or not chunks:
        return chunks[:top_k]

    pairs = [(query, c.get("content", "")[:max_content_len]) for c in chunks]
    try:
        scores = model.predict(pairs)
    except Exception as e:
        logger.warning("Reranker predict failed: %s, returning original order", e)
        return chunks[:top_k]

    scored = list(zip(scores, chunks))
    scored.sort(key=lambda x: x[0], reverse=True)

    logger.info(
        "Reranker: %d chunks scored, top-3 scores: %.3f, %.3f, %.3f",
        len(scored),
        scored[0][0] if scored else 0,
        scored[1][0] if len(scored) > 1 else 0,
        scored[2][0] if len(scored) > 2 else 0,
    )

    return [chunk for _, chunk in scored[:top_k]]
