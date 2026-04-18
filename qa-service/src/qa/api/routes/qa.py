"""API роут для QA с LightRAG."""

import asyncio
import logging
import time

import nest_asyncio
from fastapi import APIRouter, HTTPException

from ...config.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_WITH_CONTEXT, QUERY_EXPAND_PROMPT
from ...models.request import QARequest, QAResponse
from ...llm import get_llm_pool
from ...llm.config import get_llm_config

nest_asyncio.apply()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])


def _get_timeouts() -> dict:
    """Получить таймауты из конфига.

    Returns:
        Словарь с таймаутами для разных операций
    """
    config = get_llm_config()
    return {
        "lightrag": config.answer_generation_timeout,
        "query_expansion": config.query_expansion_timeout,
    }


async def expand_question(question: str) -> str:
    """Расширить вопрос с помощью LLM для лучшего поиска.

    Args:
        question: оригинальный вопрос пользователя

    Returns:
        расширенный запрос для поиска (или оригинальный вопрос при ошибке)
    """
    config = get_llm_config()
    timeout = config.query_expansion_timeout

    llm_pool = get_llm_pool()
    provider_name = llm_pool.select_model()
    if not provider_name:
        logger.warning("No LLM provider for query expansion, using original")
        return question

    try:
        prompt = f"{QUERY_EXPAND_PROMPT}\n\nВопрос студента: {question}\n\nРасширенный запрос:"
        response = await asyncio.wait_for(
            llm_pool.call(prompt=prompt),
            timeout=timeout,
        )
        expanded = response.content.strip()
        logger.info(f"Expanded query: {expanded[:100]}...")
        return expanded
    except asyncio.TimeoutError:
        logger.warning(f"Query expansion timeout after {timeout}s")
        return question
    except Exception as e:
        logger.warning(f"Query expansion failed: {e}")
        return question


@router.post("", response_model=QAResponse)
async def ask_question(request: QARequest) -> QAResponse:
    """Задать вопрос QA системе с LightRAG.

    Сначала расширяет вопрос для лучшего поиска.
    """
    from lightrag import QueryParam
    from ...main import get_lightrag, is_lightrag_ready

    config = get_llm_config()
    timeouts = _get_timeouts()
    start_time = time.time()

    if not is_lightrag_ready():
        raise HTTPException(status_code=503, detail="LightRAG not initialized")

    try:
        expanded_query = await expand_question(request.question)
        if expanded_query and len(expanded_query) > 5000:
            logger.warning(f"Expanded query truncated from {len(expanded_query)} to 5000 characters")
            expanded_query = expanded_query[:5000]
        logger.info(f"Expanded query: {(expanded_query[:100] + '...') if expanded_query else 'None'}")

        logger.info(f"Querying LightRAG for: {request.question[:50]}...")
        rag = get_lightrag()
        result = await asyncio.wait_for(
            rag.aquery(request.question, param=QueryParam(mode="mix")),
            timeout=timeouts["lightrag"],
        )
        elapsed = time.time() - start_time
        logger.info(f"LightRAG query completed in {elapsed:.2f}s")

        return QAResponse(
            answer=result,
            model="lightrag-mix",
            sources=[],
            expanded_query=expanded_query,
        )

    except asyncio.TimeoutError:
        logger.error(f"LightRAG timeout after {timeouts['lightrag']}s")
        raise HTTPException(
            status_code=503,
            detail="Сервис временно перегружен. Попробуйте повторить запрос позже.",
        )

    except Exception as e:
        logger.error(f"LightRAG query failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось сформировать ответ. Попробуйте переформулировать вопрос.",
        )
