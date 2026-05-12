"""API роут для QA с JSON-ответом LLM."""

import asyncio
import logging
import time
import uuid

import nest_asyncio
from fastapi import APIRouter, Header, HTTPException

from ...config.prompts import (
    DIALOG_CONTEXT_PROMPT,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_NO_CONTEXT,
    SYSTEM_PROMPT_ABOUT_BOT,
    SYSTEM_PROMPT_WITH_CONTEXT,
)
from ...models.request import QARequest, QAResponse, SourceLink
from ...llm import get_llm_pool
from ...llm.config import get_llm_config
from ...services.question_router import (
    QUESTION_TYPE_GENERAL,
    QUESTION_TYPE_KB,
    QUESTION_TYPE_SYSTEM,
    classify_and_expand,
)
from ...services.payload_builder import build_messages, build_no_context_messages
from ...services.response_processor import (
    build_source_links,
    clean_markdown,
    format_answer,
    parse_llm_json_response,
)

nest_asyncio.apply()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])

SEARCH_TOP_K = 5


def _get_timeouts() -> dict:
    config = get_llm_config()
    total_timeout = getattr(config, "answer_generation_timeout", 60) or 60
    return {
        "total": total_timeout,
        "lightrag": total_timeout - 10,
        "generation": total_timeout,
    }


def _format_search_context(data: dict) -> tuple[str, dict[str, str]]:
    """Преобразовать результат aquery_data в текстовый контекст для LLM.

    Каждый чанк с URL помечается номером [источник N].

    Args:
        data: Результат LightRAG aquery_data.

    Returns:
        Кортеж (контекст, маппинг {номер: URL}).
    """
    if data.get("status") != "success":
        return "", {}

    result_data = data.get("data", {})
    parts = []
    source_index: dict[str, str] = {}
    counter = 1

    chunks = result_data.get("chunks", [])
    if chunks:
        chunk_texts = []
        for chunk in chunks:
            content = chunk.get("content", "")
            file_path = chunk.get("file_path", "")
            if content:
                text = content.strip()
                if file_path and file_path.startswith("http"):
                    tag = f"[источник {counter}]"
                    source_index[str(counter)] = file_path
                    text += f"\n{tag}"
                    counter += 1
                elif file_path:
                    text += f"\nИсточник: {file_path}"
                chunk_texts.append(text)
        if chunk_texts:
            parts.append("--- Найденная информация ---\n" + "\n---\n".join(chunk_texts))

    entities = result_data.get("entities", [])
    if entities:
        entity_lines = []
        for entity in entities[:15]:
            name = entity.get("entity_name", "")
            desc = entity.get("description", "")
            if name:
                desc_short = desc[:100] if desc else ""
                entity_lines.append(f"{name}: {desc_short}" if desc_short else name)
        if entity_lines:
            parts.append("--- Сущности ---\n" + "\n".join(entity_lines))

    relationships = result_data.get("relationships", [])
    if relationships:
        rel_lines = []
        for rel in relationships[:10]:
            src = rel.get("src_id", "")
            tgt = rel.get("tgt_id", "")
            desc = rel.get("description", "")
            if src and tgt:
                desc_short = desc[:100] if desc else ""
                rel_lines.append(f"{src} → {tgt}: {desc_short}")
        if rel_lines:
            parts.append("--- Связи ---\n" + "\n".join(rel_lines))

    return "\n\n".join(parts), source_index

def _extract_keywords_from_data(data: dict) -> dict:
    """Извлечь ключевые слова из метаданных результата поиска."""
    metadata = data.get("metadata", {})
    keywords = metadata.get("keywords", {})
    return {
        "high_level": keywords.get("high_level", []),
        "low_level": keywords.get("low_level", []),
    }


def _safe_clean_answer(raw_content: str) -> str:
    """Очистить и форматировать текстовый ответ LLM.

    Args:
        raw_content: Сырой ответ от LLM.

    Returns:
        Очищенный текст ответа.

    Raises:
        ValueError: Если ответ пустой.
    """
    if not raw_content or not raw_content.strip():
        raise ValueError("LLM returned empty response")
    cleaned = clean_markdown(raw_content)
    return format_answer(cleaned)


@router.post("", response_model=QAResponse)
async def ask_question(
    request: QARequest,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> QAResponse:
    """Задать вопрос QA системе."""
    from ...main import is_lightrag_ready

    req_id = x_request_id or uuid.uuid4().hex[:8]
    timeouts = _get_timeouts()
    start_time = time.time()

    logger.info(
        f"[{req_id}] {'=' * 60}\n" f'[{req_id}] New question: "{request.question}"'
    )

    if not is_lightrag_ready():
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        async with asyncio.timeout(timeouts["total"]):
            classification = await classify_and_expand(
                request.question,
                request_id=req_id,
                dialog_context=request.context,
            )
            question_type = classification.question_type
            search_query = (
                classification.context_expanded_query
                or classification.expanded_query
                or request.question
            )

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

            if question_type == QUESTION_TYPE_KB:
                result = await _handle_kb_question(
                    req_id,
                    search_query,
                    request.question,
                    request.context,
                    llm_pool,
                    config,
                    timeouts,
                    start_time,
                )
            elif question_type == QUESTION_TYPE_SYSTEM:
                result = await _handle_system_question(
                    req_id,
                    request.question,
                    request.context,
                    llm_pool,
                    config,
                    timeouts,
                    start_time,
                )
            else:
                result = await _handle_general_question(
                    req_id,
                    request.question,
                    request.context,
                    llm_pool,
                    config,
                    timeouts,
                    start_time,
                )

            result.expanded_query = classification.expanded_query
            result.question_type = question_type
            result.context_expanded_query = classification.context_expanded_query

            total_elapsed = time.time() - start_time
            logger.info(
                f"[{req_id}] {'=' * 60}\n"
                f"[{req_id}] COMPLETE — {total_elapsed:.1f}s, "
                f"type={question_type}, "
                f"sources={len(result.sources)}, "
                f"answer_len={len(result.answer)}\n"
                f"[{req_id}] {'=' * 60}"
            )

            return result

    except asyncio.TimeoutError:
        total_elapsed = time.time() - start_time
        logger.error(f"[{req_id}] TIMEOUT after {total_elapsed:.1f}s")
        raise HTTPException(status_code=504, detail="QA pipeline timeout")

    except Exception as e:
        total_elapsed = time.time() - start_time
        logger.error(f"[{req_id}] FAILED after {total_elapsed:.1f}s: {e}")
        raise HTTPException(status_code=500, detail=f"QA pipeline error: {e}")


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
    """Обработка вопроса к базе знаний: поиск + генерация с JSON-ответом."""
    from lightrag import QueryParam
    from ...main import get_lightrag

    t2_start = time.time()
    rag = get_lightrag()

    search_context = ""
    source_index: dict[str, str] = {}
    keywords: dict = {"high_level": [], "low_level": []}

    try:
        logger.info(
            f"[{req_id}] Phase 2a START: aquery_data(mode=mix, top_k={SEARCH_TOP_K})\n"
            f"[{req_id}]   search_query: '{search_query[:120]}'"
        )

        search_data = await asyncio.wait_for(
            rag.aquery_data(
                search_query,
                param=QueryParam(mode="mix", top_k=SEARCH_TOP_K),
            ),
            timeout=timeouts["lightrag"],
        )
        t2_elapsed = time.time() - t2_start

        search_context, source_index = _format_search_context(search_data)
        keywords = _extract_keywords_from_data(search_data)

        logger.info(
            f"[{req_id}] Phase 2a DONE: search — {t2_elapsed:.1f}s\n"
            f"[{req_id}]   context_len={len(search_context)}, "
            f"sources_indexed={len(source_index)}, "
            f"keywords_HL={keywords.get('high_level', [])[:5]}"
        )
    except (asyncio.TimeoutError, Exception) as search_err:
        t2_elapsed = time.time() - t2_start
        logger.warning(
            f"[{req_id}] Phase 2a FAILED: {search_err} — {t2_elapsed:.1f}s, "
            f"falling back to LLM without KB context"
        )

    if not search_context.strip():
        logger.info(
            f"[{req_id}] No search context, generating answer without KB"
        )
        return await _generate_no_kb_answer(
            req_id,
            original_question,
            dialog_context,
            llm_pool,
            timeouts,
            start_time,
            keywords,
        )

    # ── Есть контекст: SYSTEM_PROMPT_WITH_CONTEXT + JSON ответ ──
    t3_start = time.time()
    messages = build_messages(
        system_prompt=SYSTEM_PROMPT_WITH_CONTEXT,
        question=original_question,
        search_context=search_context,
        dialog_context=dialog_context,
        dialog_context_prompt=DIALOG_CONTEXT_PROMPT,
    )

    logger.info(
        f"[{req_id}] Phase 2b START: generate with context (JSON mode)\n"
        f"[{req_id}]   system_prompt_len={len(messages[0]['content'])}\n"
        f"[{req_id}]   user_prompt_len={len(messages[1]['content'])}"
    )

    response = await asyncio.wait_for(
        llm_pool.call(prompt="", messages=messages),
        timeout=timeouts["generation"],
    )
    t3_elapsed = time.time() - t3_start

    raw_answer = response.content
    logger.info(
        f"[{req_id}] Phase 2b DONE: generation — {t3_elapsed:.1f}s\n"
        f"[{req_id}]   model={response.model}, "
        f"raw_answer_len={len(raw_answer)}"
    )

    # ── Парсинг JSON ответа ──
    parsed = parse_llm_json_response(raw_answer)

    answer = format_answer(parsed.answer)

    source_links: list[SourceLink] = []

    if parsed.relevant_sources:
        source_links = build_source_links(parsed.relevant_sources, source_index)

    logger.info(
        f"[{req_id}] Parsed: "
        f"relevant={parsed.relevant_sources}, "
        f"source_links={len(source_links)}"
    )

    total_elapsed = time.time() - start_time
    logger.info(
        f"[{req_id}] Pipeline DONE: {total_elapsed:.1f}s"
    )

    return QAResponse(
        answer=answer,
        model=response.model,
        sources=source_links,
        keywords=keywords,
        relevant_sources=parsed.relevant_sources,
    )


async def _generate_no_kb_answer(
    req_id: str,
    original_question: str,
    dialog_context: str | None,
    llm_pool,
    timeouts: dict,
    start_time: float,
    keywords: dict,
) -> QAResponse:
    """Генерация ответа без контекста из БЗ (SYSTEM_PROMPT_NO_CONTEXT)."""
    logger.info(f"[{req_id}] Generating answer with SYSTEM_PROMPT_NO_CONTEXT")

    messages = build_no_context_messages(
        system_prompt=SYSTEM_PROMPT_NO_CONTEXT,
        question=original_question,
        dialog_context=dialog_context,
        dialog_context_prompt=DIALOG_CONTEXT_PROMPT,
    )

    response = await asyncio.wait_for(
        llm_pool.call(prompt="", messages=messages),
        timeout=timeouts["generation"],
    )

    clean_answer = _safe_clean_answer(response.content)

    logger.info(
        f"[{req_id}] No-KB answer done: model={response.model}, "
        f"answer_len={len(clean_answer)}"
    )

    return QAResponse(
        answer=clean_answer,
        model=response.model,
        sources=[],
        keywords=keywords,
    )


async def _handle_system_question(
    req_id: str,
    question: str,
    dialog_context: str | None,
    llm_pool,
    config,
    timeouts: dict,
    start_time: float,
) -> QAResponse:
    """Обработка вопроса о системе/боте."""
    t2_start = time.time()

    messages = build_messages(
        system_prompt=SYSTEM_PROMPT_ABOUT_BOT,
        question=question,
        dialog_context=dialog_context,
        dialog_context_prompt=DIALOG_CONTEXT_PROMPT,
    )

    logger.info(f"[{req_id}] Phase 2 START: system question, no search")

    response = await asyncio.wait_for(
        llm_pool.call(prompt="", messages=messages),
        timeout=timeouts["generation"],
    )
    t2_elapsed = time.time() - t2_start

    clean_answer = _safe_clean_answer(response.content)

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
    dialog_context: str | None,
    llm_pool,
    config,
    timeouts: dict,
    start_time: float,
) -> QAResponse:
    """Обработка общего вопроса (приветствие, поболтать)."""
    t2_start = time.time()

    messages = build_messages(
        system_prompt=SYSTEM_PROMPT,
        question=question,
        dialog_context=dialog_context,
        dialog_context_prompt=DIALOG_CONTEXT_PROMPT,
    )

    logger.info(f"[{req_id}] Phase 2 START: general question, no search")

    response = await asyncio.wait_for(
        llm_pool.call(prompt="", messages=messages),
        timeout=timeouts["generation"],
    )
    t2_elapsed = time.time() - t2_start

    clean_answer = _safe_clean_answer(response.content)

    logger.info(
        f"[{req_id}] Phase 2 DONE: general — {t2_elapsed:.1f}s, "
        f"model={response.model}"
    )

    return QAResponse(
        answer=clean_answer,
        model=response.model,
        sources=[],
    )
