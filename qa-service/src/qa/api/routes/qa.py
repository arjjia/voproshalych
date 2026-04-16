"""API роут для QA с LightRAG."""

import asyncio
import logging
import time

import nest_asyncio
from fastapi import APIRouter, HTTPException

from ...config.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_WITH_CONTEXT, QUERY_EXPAND_PROMPT
from ...models.request import QARequest, QAResponse
from ...llm import get_llm_pool

nest_asyncio.apply()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])

LIGHTRAG_TIMEOUT_SECONDS = 20
QUERY_EXPANSION_TIMEOUT_SECONDS = 10


async def expand_question(question: str) -> str:
    """Расширить вопрос с помощью LLM для лучшего поиска.

    Args:
        question: оригинальный вопрос пользователя

    Returns:
        расширенный запрос для поиска (или оригинальный вопрос при ошибке)
    """
    llm_pool = get_llm_pool()
    provider_name = llm_pool.select_model()
    if not provider_name:
        logger.warning("No LLM provider for query expansion, using original")
        return question

    try:
        prompt = f"{QUERY_EXPAND_PROMPT}\n\nВопрос студента: {question}\n\nРасширенный запрос:"
        response = await asyncio.wait_for(
            llm_pool.call(prompt=prompt),
            timeout=QUERY_EXPANSION_TIMEOUT_SECONDS,
        )
        expanded = response.content.strip()
        logger.info(f"Expanded query: {expanded[:100]}...")
        return expanded
    except asyncio.TimeoutError:
        logger.warning(f"Query expansion timeout after {QUERY_EXPANSION_TIMEOUT_SECONDS}s")
        return question
    except Exception as e:
        logger.warning(f"Query expansion failed: {e}")
        return question


@router.post("", response_model=QAResponse)
async def ask_question(request: QARequest) -> QAResponse:
    """Задать вопрос через LightRAG (гибридный поиск: вектора + граф).

    Всегда использует LightRAG с гибридным поиском (vector + graph).
    Сначала расширяет вопрос для лучшего поиска.
    """
    start_time = time.time()

    if not is_lightrag_ready():
        raise HTTPException(status_code=503, detail="LightRAG not initialized")

    try:
        expanded_query = await expand_question(request.question)
        logger.info(f"Expanded query: {expanded_query[:100]}...")

        logger.info(f"Querying LightRAG for: {request.question[:50]}...")
        from lightrag import QueryParam
        from ...main import get_lightrag, is_lightrag_ready
        rag = get_lightrag()
        result = await asyncio.wait_for(
            rag.aquery(request.question, param=QueryParam(mode="mix")),
            timeout=LIGHTRAG_TIMEOUT_SECONDS,
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
        logger.error(f"LightRAG timeout after {LIGHTRAG_TIMEOUT_SECONDS}s")
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
