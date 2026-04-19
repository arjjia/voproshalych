"""API роут для QA с LightRAG."""

import asyncio
import logging
import time

import nest_asyncio
from fastapi import APIRouter, HTTPException

from ...config.prompts import QUERY_EXPAND_PROMPT
from ...models.request import QARequest, QAResponse
from ...llm import get_llm_pool
from ...llm.config import get_llm_config

nest_asyncio.apply()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])


def _get_timeouts() -> dict:
    config = get_llm_config()
    return {
        "lightrag": config.answer_generation_timeout,
        "query_expansion": config.query_expansion_timeout,
    }


async def expand_question(question: str) -> str:
    """Преобразовать неформальный вопрос в формальный для улучшения поиска.

    Исправляет сленг, опечатки, неформальные формулировки студентов
    (физра → физическая культура, закрыть предмет → сдать дисциплину).
    Расширенный запрос используется для keyword extraction и векторного поиска.
    """
    config = get_llm_config()
    timeout = config.query_expansion_timeout

    llm_pool = get_llm_pool()
    provider_name = llm_pool.select_model()
    if not provider_name:
        logger.warning("[PIPELINE] No LLM provider for query expansion, using original")
        return question

    try:
        prompt = f"{QUERY_EXPAND_PROMPT}\n\nВопрос студента: {question}\n\nРасширенный запрос:"
        response = await asyncio.wait_for(
            llm_pool.call(prompt=prompt),
            timeout=timeout,
        )
        expanded = response.content.strip()
        return expanded
    except asyncio.TimeoutError:
        logger.warning(f"[PIPELINE] Query expansion timeout after {timeout}s")
        return question
    except Exception as e:
        logger.warning(f"[PIPELINE] Query expansion failed: {e}")
        return question


@router.post("", response_model=QAResponse)
async def ask_question(request: QARequest) -> QAResponse:
    """Задать вопрос QA системе с LightRAG."""
    from lightrag import QueryParam
    from ...main import get_lightrag, is_lightrag_ready
    from ...lightrag_adapter import get_last_extracted_keywords

    timeouts = _get_timeouts()
    start_time = time.time()

    logger.info(
        f"[PIPELINE] {'=' * 60}\n"
        f'[PIPELINE] New question: "{request.question}"'
    )

    if not is_lightrag_ready():
        raise HTTPException(status_code=503, detail="LightRAG not initialized")

    try:
        # ── Phase 1: Query Expansion (Nemotron via LLM Pool) ──
        t1 = time.time()
        expanded_query = await expand_question(request.question)
        if expanded_query and len(expanded_query) > 5000:
            expanded_query = expanded_query[:5000]
        t1_elapsed = time.time() - t1
        logger.info(
            f"[PIPELINE] Phase 1 DONE: Query Expansion — {t1_elapsed:.1f}s\n"
            f'[PIPELINE]   expanded: "{expanded_query[:120]}"'
        )

        # ── Phase 2: LightRAG Search (keywords + graph + vector + answer) ──
        t2 = time.time()
        search_query = expanded_query or request.question
        logger.info(
            f"[PIPELINE] Phase 2 START: LightRAG aquery(mode=mix)\n"
            f'[PIPELINE]   search_query: "{search_query[:120]}"'
        )
        rag = get_lightrag()
        result = await asyncio.wait_for(
            rag.aquery(search_query, param=QueryParam(mode="mix")),
            timeout=timeouts["lightrag"],
        )
        t2_elapsed = time.time() - t2

        keywords = get_last_extracted_keywords()

        logger.info(
            f"[PIPELINE] Phase 2 DONE: LightRAG — {t2_elapsed:.1f}s\n"
            f"[PIPELINE]   keywords HL: {keywords.get('high_level', [])}\n"
            f"[PIPELINE]   keywords LL: {keywords.get('low_level', [])}"
        )

        # ── Summary ──
        total_elapsed = time.time() - start_time
        logger.info(
            f"[PIPELINE] {'=' * 60}\n"
            f"[PIPELINE] Complete — {total_elapsed:.1f}s "
            f"(expansion: {t1_elapsed:.1f}s, "
            f"lightrag: {t2_elapsed:.1f}s)\n"
            f"[PIPELINE] {'=' * 60}"
        )

        return QAResponse(
            answer=result,
            model="lightrag-mix",
            sources=[],
            expanded_query=expanded_query,
            keywords=keywords,
        )

    except asyncio.TimeoutError:
        logger.error(f"[PIPELINE] TIMEOUT after {timeouts['lightrag']}s")
        raise HTTPException(
            status_code=503,
            detail="Сервис временно перегружен. Попробуйте повторить запрос позже.",
        )

    except Exception as e:
        logger.error(f"[PIPELINE] FAILED: {e}")
        raise HTTPException(
            status_code=500,
            detail="Не удалось сформировать ответ. Попробуйте переформулировать вопрос.",
        )
