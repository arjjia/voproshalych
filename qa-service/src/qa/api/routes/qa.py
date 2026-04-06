"""API роут для QA с LightRAG и fallback на classic RAG."""

import asyncio
import logging
import time

import nest_asyncio
from fastapi import APIRouter, HTTPException

from ...config.prompts import (
    DIALOG_CONTEXT_PROMPT,
    NO_DOCUMENT_DATA_RESPONSE,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_CONTEXT,
)
from ...models.request import QARequest, QAResponse
from ...llm import get_llm_pool
from ...kb.embedding import get_embedding
from ...kb.search import search_chunks, build_context_from_chunks

nest_asyncio.apply()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])

LIGHTRAG_TIMEOUT_SECONDS = 20
CLASSIC_RAG_TIMEOUT_SECONDS = 15


def _normalize_context(context: str | None) -> str | None:
    """Нормализовать необязательный строковый контекст."""
    if context is None:
        return None

    normalized = context.strip()
    return normalized or None


def _build_lightrag_question(question: str, dialog_context: str | None) -> str:
    """Подготовить запрос в LightRAG с учетом истории диалога."""
    dialog_context = _normalize_context(dialog_context)
    if not dialog_context:
        return question

    return (
        f"{DIALOG_CONTEXT_PROMPT}\n\n"
        f"История текущего диалога:\n{dialog_context}\n\n"
        f"Последний вопрос пользователя: {question}"
    )


def _build_classic_rag_prompt(
    question: str,
    kb_context: str | None,
    dialog_context: str | None,
) -> str:
    """Собрать итоговый промпт для classic RAG."""
    dialog_context = _normalize_context(dialog_context)
    kb_context = _normalize_context(kb_context)

    prompt_parts = [SYSTEM_PROMPT_WITH_CONTEXT if kb_context else SYSTEM_PROMPT]

    if dialog_context:
        prompt_parts.append(DIALOG_CONTEXT_PROMPT)
        prompt_parts.append(f"История текущего диалога:\n{dialog_context}")

    if kb_context:
        prompt_parts.append(f"Контекст из документов ТюмГУ:\n{kb_context}")

    prompt_parts.append(f"Вопрос: {question}")
    return "\n\n".join(prompt_parts)


async def _query_lightrag(
    question: str,
    dialog_context: str | None = None,
) -> QAResponse:
    """Запрос через LightRAG."""
    from lightrag import QueryParam
    from ...main import get_lightrag, is_lightrag_ready

    if not is_lightrag_ready():
        raise RuntimeError("LightRAG not ready")

    rag = get_lightrag()
    query = _build_lightrag_question(question, dialog_context)

    try:
        result = await rag.aquery(query, param=QueryParam(mode="mix"))
        return QAResponse(
            answer=result,
            model="lightrag-mix",
            sources=[],
        )
    except Exception as e:
        logger.error(f"LightRAG query failed: {e}")
        raise


async def _query_classic_rag(
    question: str,
    dialog_context: str | None = None,
) -> QAResponse:
    """Запрос через классический RAG с pgvector."""
    llm_pool = get_llm_pool()

    try:
        context = ""
        sources = []
        chunks: list[dict] = []

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
            else:
                logger.info("Classic RAG found 0 relevant chunks")
        except Exception as e:
            logger.warning(f"KB search failed in classic RAG: {e}")

        if not chunks:
            return QAResponse(
                answer=NO_DOCUMENT_DATA_RESPONSE,
                model="kb-search",
                sources=[],
            )

        provider_name = llm_pool.select_model()
        if not provider_name:
            raise HTTPException(status_code=503, detail="No available LLM providers")

        prompt = _build_classic_rag_prompt(
            question=question,
            kb_context=context,
            dialog_context=dialog_context,
        )

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
    """Задать вопрос с LightRAG (primary) + fallback на classic RAG.

    Pipeline:
    1. Попытка LightRAG (timeout: 20s)
    2. При ошибке/таймауте -> classic RAG (timeout: 15s)
    3. При ошибке classic RAG -> user-friendly error
    """
    use_lightrag = True
    dialog_context = _normalize_context(request.context)

    if use_lightrag:
        start_time = time.time()

        try:
            logger.info(f"Querying LightRAG for: {request.question[:50]}...")
            result = await asyncio.wait_for(
                _query_lightrag(
                    request.question,
                    dialog_context=dialog_context,
                ),
                timeout=LIGHTRAG_TIMEOUT_SECONDS,
            )
            elapsed = time.time() - start_time
            logger.info(f"LightRAG query completed in {elapsed:.2f}s")
            return result

        except asyncio.TimeoutError:
            logger.warning(
                f"LightRAG timeout after {LIGHTRAG_TIMEOUT_SECONDS}s, falling back to classic RAG"
            )
            fallback_reason = "timeout"

        except Exception as e:
            logger.warning(f"LightRAG failed: {e}, falling back to classic RAG")
            fallback_reason = f"error: {type(e).__name__}"

        start_time = time.time()

        try:
            logger.info(f"Falling back to classic RAG for: {request.question[:50]}...")
            result = await asyncio.wait_for(
                _query_classic_rag(
                    request.question,
                    dialog_context=dialog_context,
                ),
                timeout=CLASSIC_RAG_TIMEOUT_SECONDS,
            )
            elapsed = time.time() - start_time
            logger.info(
                f"Classic RAG query completed in {elapsed:.2f}s (fallback: {fallback_reason})"
            )
            return result

        except asyncio.TimeoutError:
            logger.error(f"Classic RAG also timed out")
            raise HTTPException(
                status_code=503,
                detail="Сервис временно перегружен. Попробуйте повторить запрос позже.",
            )

        except Exception as e:
            logger.error(f"Classic RAG also failed: {e}")
            raise HTTPException(
                status_code=500,
                detail="Не удалось сформировать ответ. Попробуйте переформулировать вопрос.",
            )
    else:
        return await _query_classic_rag(
            request.question,
            dialog_context=dialog_context,
        )


@router.post("/lightrag", response_model=QAResponse)
async def ask_question_lightrag(request: QARequest) -> QAResponse:
    """Запрос исключительно через LightRAG (без fallback)."""
    try:
        return await _query_lightrag(
            request.question,
            dialog_context=request.context,
        )
    except Exception as e:
        logger.error(f"LightRAG query failed: {e}")
        raise HTTPException(status_code=500, detail=f"LightRAG error: {str(e)}")


@router.post("/classic", response_model=QAResponse)
async def ask_question_classic(request: QARequest) -> QAResponse:
    """Запрос исключительно через классический RAG."""
    try:
        return await _query_classic_rag(
            request.question,
            dialog_context=request.context,
        )
    except Exception as e:
        logger.error(f"Classic RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Classic RAG error: {str(e)}")
