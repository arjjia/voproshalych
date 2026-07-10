"""Question classification and expansion for KB search.

Port of v2 qa-service question_router.py logic.
"""

import json
import logging
import re
import time

import httpx

from kb.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

QUESTION_TYPE_KB = 1
QUESTION_TYPE_SYSTEM = 2
QUESTION_TYPE_GENERAL = 3

DEFAULT_TIMEOUT = 20.0

GLOSSARY_TYUMSU = """Справочник аббревиатур и сленга ТюмГУ:

Аббревиатуры:
- ЕЛК — единый личный кабинет
- ЕД — единый деканат
- ОФО — очная форма обучения
- ОЗФО — очно-заочная форма обучения
- ЗФО — заочная форма обучения
- ЕГРЮЛ — единый государственный реестр юридических лиц
- ПА — промежуточная аттестация
- ППА — первая повторная аттестация
- ВПА — вторая повторная аттестация
- ЦИТ — центр информационных технологий

Институты:
- ШКН — школа компьютерных наук
- ИГиП — институт государства и права
- ФЭИ — финансово-экономический институт
- ШО — школа образования
- СоцГум — институт социально-гуманитарных наук
- ФТИ — физико-технический институт
- ИнХим — институт химии
- ШЕН — школа естественных наук
- ИнБио — институт экологической и сельскохозяйственной биологии (X-BIO)
"""

QUERY_CLASSIFY_EXPAND_PROMPT = f"""{GLOSSARY_TYUMSU}

Определи тип вопроса и нормализуй его для поиска.

Типы:
1 — вопрос к базе знаний ТюмГУ (обучение, документы, расписания, общежитие, стипендия и т.д.)
2 — вопрос о самом боте (кто создал, что умеешь, как зовут)
3 — всё остальное (приветствие, шутки, код, общие темы, болтовня)

ПРАВИЛО: не про ТюмГУ и не про бота = тип 3.

Нормализация (только тип 1):
- Расшифруй аббревиатуры и сленг по справочнику выше
- Исправь опечатки
- Аббревиатуры: всегда оба варианта (аббревиатура + расшифровка)
- Не добавляй синонимы, не расширяй
- Тип 2 и 3: expanded_query = оригинал без изменений

Учёт контекста диалога (только тип 1):
Если передана история — свяжи вопрос с контекстом: добавь ключевые термины из диалога в context_expanded_query.

Верни СТРОГО JSON:
{{"type": 1, "expanded_query": "...", "context_expanded_query": "..."}}"""


class QuestionClassification:
    """Result of question classification."""

    __slots__ = ("question_type", "expanded_query", "confidence", "context_expanded_query")

    def __init__(
        self,
        question_type: int = QUESTION_TYPE_KB,
        expanded_query: str = "",
        confidence: float = 0.0,
        context_expanded_query: str | None = None,
    ):
        self.question_type = question_type
        self.expanded_query = expanded_query
        self.confidence = confidence
        self.context_expanded_query = context_expanded_query


async def classify_and_expand(
    question: str,
    dialog_context: str = "",
    settings: Settings | None = None,
) -> QuestionClassification:
    """Classify question and expand query for search.

    One LLM call determines question type (1=KB, 2=system, 3=general),
    normalizes the query and (for type 1) expands it with dialog context.

    On error/timeout returns type=1 (fail-safe = knowledge base)
    with the original question.

    Args:
        question: Original user question.
        dialog_context: Dialog history (original).
        settings: Application settings.

    Returns:
        QuestionClassification with type and expanded query.
    """
    s = settings or default_settings
    timeout = DEFAULT_TIMEOUT

    try:
        prompt_parts = [QUERY_CLASSIFY_EXPAND_PROMPT]

        if dialog_context and dialog_context.strip():
            prompt_parts.append(
                f"История диалога:\n{dialog_context}\n"
            )

        prompt_parts.append(f"Вопрос: {question}")
        prompt_parts.append("Ответ (только JSON):")

        prompt = "\n\n".join(prompt_parts)

        logger.info(
            f"[CLASSIFY] classify_and_expand, "
            f"question='{question[:100]}'"
        )
        t_start = time.time()

        url = f"{s.litellm_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {s.litellm_master_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": s.classifier_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 256,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"].strip()

        elapsed = time.time() - t_start

        logger.info(
            f"[CLASSIFY] LLM_RESPONSE: '{raw_content[:300]}' "
            f"({elapsed:.1f}s)"
        )

        result = _parse_classification_response(raw_content, question)

        logger.info(
            f"[CLASSIFY] DONE: type={result.question_type}, "
            f"expanded='{result.expanded_query[:120]}', "
            f"confidence={result.confidence:.2f} ({elapsed:.1f}s)"
        )
        return result

    except Exception as e:
        logger.warning(
            f"[CLASSIFY] FAILED: {e}, "
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
    """Parse classification JSON response.

    Args:
        raw_content: Raw LLM response.
        original_question: Original question (fallback).

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

        context_expanded = parsed.get("context_expanded_query")
        if context_expanded is not None:
            if not isinstance(context_expanded, str) or not context_expanded.strip():
                context_expanded = None
            elif len(context_expanded) > 1500:
                context_expanded = context_expanded[:1500]

        confidence = parsed.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5

        return QuestionClassification(
            question_type=q_type,
            expanded_query=expanded.strip(),
            confidence=float(confidence),
            context_expanded_query=context_expanded.strip() if context_expanded else None,
        )

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[CLASSIFY] Parse failed: {e}, raw='{raw_content[:200]}'")
        return QuestionClassification(
            question_type=QUESTION_TYPE_KB,
            expanded_query=original_question,
        )
