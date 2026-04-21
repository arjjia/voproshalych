"""API роут для QA с разделённым поиском и генерацией."""

import asyncio
import logging
import time
import uuid

import nest_asyncio
from fastapi import APIRouter, Header, HTTPException

from ...config.prompts import (
    DIALOG_CONTEXT_PROMPT,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_ABOUT_BOT,
    SYSTEM_PROMPT_WITH_CONTEXT,
)
from ...models.request import QARequest, QAResponse
from ...llm import get_llm_pool
from ...llm.config import get_llm_config
from ...services.question_router import (
    QUESTION_TYPE_GENERAL,
    QUESTION_TYPE_KB,
    QUESTION_TYPE_SYSTEM,
    classify_and_expand,
)
from ...services.payload_builder import build_messages
from ...services.response_processor import process_llm_response

nest_asyncio.apply()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])


def _get_timeouts() -> dict:
    config = get_llm_config()
    return {
        "lightrag": getattr(config, "answer_generation_timeout", 120) or 120,
        "generation": getattr(config, "answer_generation_timeout", 120) or 120,
    }


def _format_search_context(data: dict) -> str:
    """Преобразовать результат aquery_data в текстовый контекст для LLM.

    Args:
        data: Результат LightRAG aquery_data.

    Returns:
        Строка с чанками, сущностями и ссылками.
    """
    if data.get("status") != "success":
        return ""

    result_data = data.get("data", {})
    parts = []

    chunks = result_data.get("chunks", [])
    if chunks:
        chunk_texts = []
        for chunk in chunks:
            content = chunk.get("content", "")
            file_path = chunk.get("file_path", "")
            if content:
                text = content.strip()
                if file_path:
                    text += f"\nИсточник: {file_path}"
                chunk_texts.append(text)
        if chunk_texts:
            parts.append("--- Найденная информация ---\n" + "\n---\n".join(chunk_texts))

    entities = result_data.get("entities", [])
    if entities:
        entity_lines = []
        for entity in entities[:30]:
            name = entity.get("entity_name", "")
            desc = entity.get("description", "")
            if name:
                entity_lines.append(f"{name}: {desc}" if desc else name)
        if entity_lines:
            parts.append("--- Сущности ---\n" + "\n".join(entity_lines))

    relationships = result_data.get("relationships", [])
    if relationships:
        rel_lines = []
        for rel in relationships[:20]:
            src = rel.get("src_id", "")
            tgt = rel.get("tgt_id", "")
            desc = rel.get("description", "")
            if src and tgt:
                rel_lines.append(f"{src} → {tgt}: {desc}")
        if rel_lines:
            parts.append("--- Связи ---\n" + "\n".join(rel_lines))

    return "\n\n".join(parts)


def _extract_sources_from_data(data: dict) -> list[str]:
    """Извлечь уникальные URL источников из результата поиска.

    Args:
        data: Результат LightRAG aquery_data.

    Returns:
        Список URL источников.
    """
    if data.get("status") != "success":
        return []

    result_data = data.get("data", {})
    chunks = result_data.get("chunks", [])
    references = result_data.get("references", [])

    sources = set()
    for chunk in chunks:
        fp = chunk.get("file_path", "")
        if fp and fp.startswith("http"):
            sources.add(fp)

    for ref in references:
        fp = ref.get("file_path", "")
        if fp and fp.startswith("http"):
            sources.add(fp)

    return list(sources)


def _extract_keywords_from_data(data: dict) -> dict:
    """Извлечь ключевые слова из метаданных результата поиска."""
    metadata = data.get("metadata", {})
    keywords = metadata.get("keywords", {})
    return {
        "high_level": keywords.get("high_level", []),
        "low_level": keywords.get("low_level", []),
    }


@router.post("", response_model=QAResponse)
async def ask_question(
    request: QARequest,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> QAResponse:
    """Задать вопрос QA системе с маршрутизацией и разделённым поиском/генерацией."""
    from lightrag import QueryParam
    from ...main import get_lightrag, is_lightrag_ready
    from ...lightrag_adapter import get_last_extracted_keywords

    req_id = x_request_id or uuid.uuid4().hex[:8]
    timeouts = _get_timeouts()
    start_time = time.time()

    logger.info(
        f"[{req_id}] {'=' * 60}\n"
        f'[{req_id}] New question: "{request.question}"'
    )

    if not is_lightrag_ready():
        raise HTTPException(status_code=503, detail="LightRAG not initialized")

    try:
        # ── Phase 1: Classify + Expand ──
        classification = await classify_and_expand(
            request.question, request_id=req_id
        )
        question_type = classification.question_type
        search_query = classification.expanded_query or request.question

        if len(search_query) > 1500:
            search_query = search_query[:1500]

        t1_elapsed = time.time() - start_time
        logger.info(
            f"[{req_id}] Phase 1 DONE: classify_and_expand — {t1_elapsed:.1f}s\n"
            f"[{req_id}]   type={question_type}, "
            f"search_query='{search_query[:120]}'"
        )

        llm_pool = get_llm_pool()
        config = get_llm_config()

        # ── Branch by question type ──
        if question_type == QUESTION_TYPE_KB:
            result = await _handle_kb_question(
                req_id, search_query, request.question,
                request.context, llm_pool, config, timeouts, start_time,
            )
        elif question_type == QUESTION_TYPE_SYSTEM:
            result = await _handle_system_question(
                req_id, request.question, llm_pool, config, timeouts, start_time,
            )
        else:
            result = await _handle_general_question(
                req_id, request.question, llm_pool, config, timeouts, start_time,
            )

        result.expanded_query = classification.expanded_query
        result.question_type = question_type

        total_elapsed = time.time() - start_time
        logger.info(
            f"[{req_id}] {'=' * 60}\n"
            f"[{req_id}] COMPLETE — {total_elapsed:.1f}s, "
            f"type={question_type}, "
            f"answer_len={len(result.answer)}, "
            f"sources={len(result.sources)}\n"
            f"[{req_id}] {'=' * 60}"
        )

        return result

    except asyncio.TimeoutError:
        total_elapsed = time.time() - start_time
        logger.error(f"[{req_id}] TIMEOUT after {total_elapsed:.1f}s")
        return QAResponse(
            answer=(
                "Не удалось быстро найти ответ. "
                "Попробуйте переформулировать вопрос — "
                "используйте простые термины и конкретные формулировки. "
                "Если не поможет, повторите чуть позже."
            ),
            model="timeout-fallback",
            question_type=1,
        )

    except Exception as e:
        total_elapsed = time.time() - start_time
        logger.error(f"[{req_id}] FAILED after {total_elapsed:.1f}s: {e}")
        return QAResponse(
            answer=(
                "Не удалось сформировать ответ. "
                "Попробуйте переформулировать вопрос — "
                "используйте простые термины и конкретные формулировки. "
                "Если не поможет, повторите позже."
            ),
            model="error-fallback",
            question_type=1,
        )


async def _handle_kb_question(
    req_id: str,
    search_query: str,
    original_question: str,
    dialog_context: str | None,
    llm_pool,
    config,
    timeouts: dict,
    start_time: float,
) -> QAResponse:
    """Обработка вопроса к базе знаний: поиск + генерация."""
    from lightrag import QueryParam
    from ...main import get_lightrag

    # ── Phase 2a: LightRAG search (no generation) ──
    t2_start = time.time()
    rag = get_lightrag()

    logger.info(
        f"[{req_id}] Phase 2a START: aquery_data(mode=mix)\n"
        f"[{req_id}]   search_query: '{search_query[:120]}'"
    )

    search_data = await asyncio.wait_for(
        rag.aquery_data(
            search_query,
            param=QueryParam(mode="mix", top_k=20, top_n=10),
        ),
        timeout=timeouts["lightrag"],
    )
    t2_elapsed = time.time() - t2_start

    search_context = _format_search_context(search_data)
    sources = _extract_sources_from_data(search_data)
    keywords = _extract_keywords_from_data(search_data)

    logger.info(
        f"[{req_id}] Phase 2a DONE: search — {t2_elapsed:.1f}s\n"
        f"[{req_id}]   context_len={len(search_context)}, "
        f"sources={len(sources)}, "
        f"keywords_HL={keywords.get('high_level', [])[:5]}"
    )

    if not search_context.strip():
        logger.info(
            f"[{req_id}] No search context found, "
            f"generating answer without KB context"
        )
        messages = build_messages(
            system_prompt=SYSTEM_PROMPT,
            question=original_question,
            search_context=None,
            dialog_context=dialog_context,
            dialog_context_prompt=DIALOG_CONTEXT_PROMPT,
        )

        response = await asyncio.wait_for(
            llm_pool.call(prompt="", messages=messages),
            timeout=timeouts["generation"],
        )
        t3_elapsed = time.time() - t2_start

        clean_answer, _ = process_llm_response(response.content)

        logger.info(
            f"[{req_id}] Phase 2 DONE (no KB context): "
            f"{t3_elapsed:.1f}s, model={response.model}"
        )

        return QAResponse(
            answer=clean_answer,
            model=response.model,
            sources=[],
            keywords=keywords,
        )

    # ── Phase 2b: Build payload + generate answer ──
    t3_start = time.time()
    messages = build_messages(
        system_prompt=SYSTEM_PROMPT_WITH_CONTEXT,
        question=original_question,
        search_context=search_context,
        dialog_context=dialog_context,
        dialog_context_prompt=DIALOG_CONTEXT_PROMPT,
    )

    logger.info(
        f"[{req_id}] Phase 2b START: generate answer\n"
        f"[{req_id}]   system_prompt_len={len(messages[0]['content'])}\n"
        f"[{req_id}]   user_prompt_len={len(messages[1]['content'])}"
    )

    response = await asyncio.wait_for(
        llm_pool.call(
            prompt="",
            messages=messages,
        ),
        timeout=timeouts["generation"],
    )
    t3_elapsed = time.time() - t3_start

    raw_answer = response.content
    logger.info(
        f"[{req_id}] Phase 2b DONE: generation — {t3_elapsed:.1f}s\n"
        f"[{req_id}]   model={response.model}, "
        f"raw_answer_len={len(raw_answer)}, "
        f"tokens={response.usage}"
    )

    # ── Phase 3: Post-processing ──
    clean_answer, answer_links = process_llm_response(raw_answer)

    all_sources = list(dict.fromkeys(sources + answer_links))

    total_elapsed = time.time() - start_time
    logger.info(
        f"[{req_id}] Pipeline DONE: {total_elapsed:.1f}s "
        f"(search={t2_elapsed:.1f}s, gen={t3_elapsed:.1f}s)"
    )

    return QAResponse(
        answer=clean_answer,
        model=response.model,
        sources=all_sources[:5],
        keywords=keywords,
    )


async def _handle_system_question(
    req_id: str,
    question: str,
    llm_pool,
    config,
    timeouts: dict,
    start_time: float,
) -> QAResponse:
    """Обработка вопроса о системе/боте."""
    t2_start = time.time()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_ABOUT_BOT},
        {"role": "user", "content": question},
    ]

    logger.info(f"[{req_id}] Phase 2 START: system question, no search")

    response = await asyncio.wait_for(
        llm_pool.call(prompt="", messages=messages),
        timeout=timeouts["generation"],
    )
    t2_elapsed = time.time() - t2_start

    clean_answer, _ = process_llm_response(response.content)

    logger.info(
        f"[{req_id}] Phase 2 DONE: system — {t2_elapsed:.1f}s, "
        f"model={response.model}"
    )

    return QAResponse(
        answer=clean_answer,
        model=response.model,
        sources=[],
    )


async def _handle_general_question(
    req_id: str,
    question: str,
    llm_pool,
    config,
    timeouts: dict,
    start_time: float,
) -> QAResponse:
    """Обработка общего вопроса (приветствие, поболтать)."""
    t2_start = time.time()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    logger.info(f"[{req_id}] Phase 2 START: general question, no search")

    response = await asyncio.wait_for(
        llm_pool.call(prompt="", messages=messages),
        timeout=timeouts["generation"],
    )
    t2_elapsed = time.time() - t2_start

    clean_answer, _ = process_llm_response(response.content)

    logger.info(
        f"[{req_id}] Phase 2 DONE: general — {t2_elapsed:.1f}s, "
        f"model={response.model}"
    )

    return QAResponse(
        answer=clean_answer,
        model=response.model,
        sources=[],
    )
