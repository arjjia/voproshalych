"""API роут для QA с LightRAG и fallback на classic RAG."""

import asyncio
import logging
import os
import time

import nest_asyncio
from fastapi import APIRouter, HTTPException

from ...config.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_WITH_CONTEXT, QUERY_EXPAND_PROMPT
from ...models.request import QARequest, QAResponse
from ...llm import get_llm_pool
from ...kb.embedding import get_embedding
from ...kb.search import search_chunks, build_context_from_chunks

nest_asyncio.apply()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])

LIGHTRAG_TIMEOUT_SECONDS = 20
CLASSIC_RAG_TIMEOUT_SECONDS = 15
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


async def _query_lightrag(question: str, expanded_query: str | None = None) -> QAResponse:
    """Запрос через LightRAG."""
    from lightrag import QueryParam
    from ...main import get_lightrag, is_lightrag_ready

    if not is_lightrag_ready():
        raise RuntimeError("LightRAG not ready")

    rag = get_lightrag()

    try:
        result = await rag.aquery(question, param=QueryParam(mode="mix"))
        return QAResponse(
            answer=result,
            model="lightrag-mix",
            sources=[],
            expanded_query=expanded_query,
        )
    except Exception as e:
        logger.error(f"LightRAG query failed: {e}")
        raise


async def _query_classic_rag(question: str) -> QAResponse:
    """Запрос через классический RAG с pgvector."""
    llm_pool = get_llm_pool()

    provider_name = llm_pool.select_model()
    if not provider_name:
        raise HTTPException(status_code=503, detail="No available LLM providers")

    try:
        context = ""
        sources = []

        try:
            query_embedding = get_embedding(question)
            chunks = await search_chunks(
                query=question,
                embedding=query_embedding,
                top_k=3,
            )
            if chunks:
                context = build_context_from_chunks(chunks)
                sources = [c["source_url"] for c in chunks if c.get("source_url")]
                logger.info(f"Classic RAG found {len(chunks)} relevant chunks")
        except Exception as e:
            logger.warning(f"KB search failed in classic RAG: {e}")

        if context:
            prompt = f"{SYSTEM_PROMPT_WITH_CONTEXT}\n\nКонтекст из документов ТюмГУ:\n{context}\n\nВопрос: {question}"
        else:
            prompt = f"{SYSTEM_PROMPT}\n\nВопрос: {question}"

        response = await llm_pool.call(prompt=prompt)

        return QAResponse(
            answer=response.content,
            model=response.model,
            sources=sources,
        )
    except Exception as e:
        logger.error(f"Classic RAG query failed: {e}")
        raise


@router.post("", response_model=QAResponse)
async def ask_question(request: QARequest) -> QAResponse:
    """Задать вопрос через LightRAG (гибридный поиск: вектора + граф).

    Всегда использует LightRAG с гибридным поиском (vector + graph).
    Сначала расширяет вопрос для лучшего поиска.
    """
    start_time = time.time()

    try:
        expanded_query = await expand_question(request.question)
        logger.info(f"Expanded query: {expanded_query[:100]}...")

        logger.info(f"Querying LightRAG for: {request.question[:50]}...")
        result = await asyncio.wait_for(
            _query_lightrag(request.question, expanded_query), timeout=LIGHTRAG_TIMEOUT_SECONDS
        )
        elapsed = time.time() - start_time
        logger.info(f"LightRAG query completed in {elapsed:.2f}s")
        return result

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


@router.post("/lightrag", response_model=QAResponse)
async def ask_question_lightrag(request: QARequest) -> QAResponse:
    """Запрос исключительно через LightRAG (без fallback)."""
    try:
        return await _query_lightrag(request.question)
    except Exception as e:
        logger.error(f"LightRAG query failed: {e}")
        raise HTTPException(status_code=500, detail=f"LightRAG error: {str(e)}")


@router.post("/classic", response_model=QAResponse)
async def ask_question_classic(request: QARequest) -> QAResponse:
    """Запрос исключительно через классический RAG."""
    try:
        return await _query_classic_rag(request.question)
    except Exception as e:
        logger.error(f"Classic RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Classic RAG error: {str(e)}")
