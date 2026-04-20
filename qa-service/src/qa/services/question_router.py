"""Маршрутизация вопросов: классификация типа + расширение запроса."""

import asyncio
import json
import logging
import re
import time

from ..config.prompts import QUERY_CLASSIFY_EXPAND_PROMPT
from ..llm import get_llm_pool
from ..llm.config import get_llm_config

logger = logging.getLogger(__name__)

QUESTION_TYPE_KB = 1
QUESTION_TYPE_SYSTEM = 2
QUESTION_TYPE_GENERAL = 3

DEFAULT_TIMEOUT = 20.0


class QuestionClassification:
    """Результат классификации вопроса."""

    __slots__ = ("question_type", "expanded_query", "confidence")

    def __init__(
        self,
        question_type: int = QUESTION_TYPE_KB,
        expanded_query: str = "",
        confidence: float = 0.0,
    ):
        self.question_type = question_type
        self.expanded_query = expanded_query
        self.confidence = confidence


async def classify_and_expand(
    question: str,
    request_id: str = "",
) -> QuestionClassification:
    """Классифицировать вопрос и расширить запрос для поиска.

    Один вызов LLM определяет тип вопроса (1=БЗ, 2=система, 3=общий)
    и расширяет запрос для лучшего поиска.

    При ошибке/таймауте возвращает type=1 (fail-safe = база знаний)
    с оригинальным вопросом.

    Args:
        question: Оригинальный вопрос пользователя.
        request_id: ID запроса для логирования.

    Returns:
        QuestionClassification с типом и расширенным запросом.
    """
    config = get_llm_config()
    timeout = getattr(config, "query_expansion_timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT

    llm_pool = get_llm_pool()
    provider_name = llm_pool.select_model()
    if not provider_name:
        logger.warning(f"[{request_id}] No LLM provider for classification")
        return QuestionClassification(
            question_type=QUESTION_TYPE_KB,
            expanded_query=question,
        )

    try:
        prompt = (
            f"{QUERY_CLASSIFY_EXPAND_PROMPT}\n\n"
            f"Вопрос: {question}\n\n"
            f"Ответ (только JSON):"
        )

        logger.info(
            f"[{request_id}] Phase 1 START: classify_and_expand, "
            f"question='{question[:100]}'"
        )
        t_start = time.time()

        response = await asyncio.wait_for(
            llm_pool.call(prompt=prompt),
            timeout=timeout,
        )

        elapsed = time.time() - t_start
        raw_content = response.content.strip()

        logger.info(
            f"[{request_id}] Phase 1 LLM_RESPONSE: '{raw_content[:300]}' "
            f"({elapsed:.1f}s)"
        )

        result = _parse_classification_response(raw_content, question)

        logger.info(
            f"[{request_id}] Phase 1 DONE: type={result.question_type}, "
            f"expanded='{result.expanded_query[:120]}', "
            f"confidence={result.confidence:.2f} ({elapsed:.1f}s)"
        )
        return result

    except asyncio.TimeoutError:
        logger.warning(
            f"[{request_id}] Phase 1 TIMEOUT after {timeout}s, "
            f"using original question"
        )
        return QuestionClassification(
            question_type=QUESTION_TYPE_KB,
            expanded_query=question,
        )
    except Exception as e:
        logger.warning(
            f"[{request_id}] Phase 1 FAILED: {e}, "
            f"using original question"
        )
        return QuestionClassification(
            question_type=QUESTION_TYPE_KB,
            expanded_query=question,
        )


def _parse_classification_response(
    raw_content: str,
    original_question: str,
) -> QuestionClassification:
    """Парсинг JSON ответа классификации.

    Args:
        raw_content: Сырой ответ LLM.
        original_question: Оригинальный вопрос (fallback).

    Returns:
        QuestionClassification.
    """
    try:
        json_match = re.search(r"\{[^{}]*\}", raw_content, re.DOTALL)
        if not json_match:
            logger.warning(
                f"[CLASSIFY] No JSON found in response: '{raw_content[:200]}'"
            )
            return QuestionClassification(
                question_type=QUESTION_TYPE_KB,
                expanded_query=original_question,
            )

        parsed = json.loads(json_match.group())

        q_type = parsed.get("type", 1)
        if not isinstance(q_type, int) or q_type not in (1, 2, 3):
            q_type = 1

        expanded = parsed.get("expanded_query", original_question)
        if not isinstance(expanded, str) or not expanded.strip():
            expanded = original_question

        if len(expanded) > 1500:
            expanded = expanded[:1500]

        confidence = parsed.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5

        return QuestionClassification(
            question_type=q_type,
            expanded_query=expanded.strip(),
            confidence=float(confidence),
        )

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[CLASSIFY] Parse failed: {e}, raw='{raw_content[:200]}'")
        return QuestionClassification(
            question_type=QUESTION_TYPE_KB,
            expanded_query=original_question,
        )
