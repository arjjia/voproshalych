"""Формирование payload для LLM с фиксированными лимитами на каждую секцию."""

import logging

logger = logging.getLogger(__name__)

GOLDEN_CHUNKS_MAX_CHARS = 800
DIALOG_CONTEXT_MAX_CHARS = 1200
SEARCH_CONTEXT_MAX_CHARS = 1500
QUESTION_MAX_CHARS = 500


def _truncate_to_limit(text: str, max_chars: int, boundary: str = "\n---\n") -> str:
    """Обрезать текст до лимита символов с сохранением целостности чанков.

    Args:
        text: Текст для обрезки.
        max_chars: Максимальное количество символов.
        boundary: Граница чанка для поиска точки обрезки.

    Returns:
        Обрезанный текст.
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_boundary = truncated.rfind(boundary)
    if last_boundary > max_chars * 0.5:
        truncated = truncated[:last_boundary]

    return truncated.strip() + "\n\n[...часть контекста опущена...]"


def build_messages(
    system_prompt: str,
    question: str,
    search_context: str | None = None,
    dialog_context: str | None = None,
    dialog_context_prompt: str | None = None,
    golden_chunks: str | None = None,
) -> list[dict]:
    """Сформировать messages[] для ChatCompletion API.

    Каждая секция имеет фиксированный лимит символов:
    - golden_chunks: до 800 символов (обрезка по границе абзаца)
    - dialog_context: до 1200 символов (обрезка по границе строки)
    - search_context: до 1500 символов (обрезка по границе \\n---\\n)
    - question: до 500 символов (жёсткая обрезка)

    Приоритет сохранения (что отбрасываем последним):
    1. system_prompt — обязателен
    2. question — обязателен
    3. search_context — важен для ответа
    4. golden_chunks — базовая информация
    5. dialog_context — наименее важен, отбрасываем первым

    Args:
        system_prompt: Системный промт.
        question: Вопрос пользователя.
        search_context: Контекст из поиска (чанки, entities).
        dialog_context: История диалога.
        dialog_context_prompt: Инструкция для контекста диалога.
        golden_chunks: Базовая информация об университете.

    Returns:
        Список сообщений [{"role": "system"/"user", "content": "..."}].
    """
    user_parts: list[str] = []

    if golden_chunks and golden_chunks.strip():
        gc = _truncate_to_limit(golden_chunks, GOLDEN_CHUNKS_MAX_CHARS, "\n\n")
        user_parts.append(f"Базовая информация о ТюмГУ:\n{gc}")

    if dialog_context and dialog_context.strip():
        dc = dialog_context
        if len(dc) > DIALOG_CONTEXT_MAX_CHARS:
            dc = dc[:DIALOG_CONTEXT_MAX_CHARS]
        ctx_header = dialog_context_prompt or "История диалога:"
        user_parts.append(f"{ctx_header}\n{dc}")

    if search_context and search_context.strip():
        sc = _truncate_to_limit(search_context, SEARCH_CONTEXT_MAX_CHARS)
        user_parts.append(f"Контекст из базы знаний:\n{sc}")

    q = question
    if len(q) > QUESTION_MAX_CHARS:
        q = q[:QUESTION_MAX_CHARS]
    user_parts.append(f"Вопрос студента: {q}")

    user_content = "\n\n".join(user_parts)

    total_chars = len(system_prompt) + len(user_content)
    total_tokens_est = total_chars // 4

    logger.info(
        f"[PAYLOAD] Sections: golden_chunks={bool(golden_chunks)}, "
        f"dialog_context={bool(dialog_context)}, "
        f"search_context={bool(search_context)}, "
        f"user_content_len={len(user_content)}, "
        f"total_chars={total_chars}, "
        f"estimated_tokens={total_tokens_est}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def build_no_context_messages(
    system_prompt: str,
    question: str,
    dialog_context: str | None = None,
    dialog_context_prompt: str | None = None,
    golden_chunks: str | None = None,
) -> list[dict]:
    """Сформировать messages для случая без контекста поиска.

    Используется для SYSTEM_PROMPT_NO_CONTEXT (ветка B).
    Отличие: нет search_context, LLM отвечает свободным текстом.

    Args:
        system_prompt: Системный промт (SYSTEM_PROMPT_NO_CONTEXT).
        question: Вопрос пользователя.
        dialog_context: История диалога.
        dialog_context_prompt: Инструкция для контекста диалога.
        golden_chunks: Базовая информация об университете.

    Returns:
        Список сообщений [{"role": "system"/"user", "content": "..."}].
    """
    user_parts: list[str] = []

    if golden_chunks and golden_chunks.strip():
        gc = _truncate_to_limit(golden_chunks, GOLDEN_CHUNKS_MAX_CHARS, "\n\n")
        user_parts.append(f"Базовая информация о ТюмГУ:\n{gc}")

    if dialog_context and dialog_context.strip():
        dc = dialog_context
        if len(dc) > DIALOG_CONTEXT_MAX_CHARS:
            dc = dc[:DIALOG_CONTEXT_MAX_CHARS]
        ctx_header = dialog_context_prompt or "История диалога:"
        user_parts.append(f"{ctx_header}\n{dc}")

    q = question
    if len(q) > QUESTION_MAX_CHARS:
        q = q[:QUESTION_MAX_CHARS]
    user_parts.append(f"Вопрос студента: {q}")

    user_content = "\n\n".join(user_parts)

    logger.info(
        f"[PAYLOAD] no_context: dialog_context={bool(dialog_context)}, "
        f"user_content_len={len(user_content)}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
