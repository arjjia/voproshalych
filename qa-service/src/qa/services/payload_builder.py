"""Формирование payload для LLM.

Источники:
- dialog_context: 3 сообщения, до 300 символов (dialog_service.build_context)
- search_context: чанки LightRAG, подготовленные QA route
- question: до 500 символов
"""

import logging

logger = logging.getLogger(__name__)

QUESTION_MAX_CHARS = 500


def build_messages(
    system_prompt: str,
    question: str,
    search_context: str | None = None,
    dialog_context: str | None = None,
    dialog_context_prompt: str | None = None,
) -> list[dict]:
    """Сформировать messages[] для ChatCompletion API.

    Args:
        system_prompt: Системный промт.
        question: Вопрос пользователя.
        search_context: Контекст из поиска (чанки).
        dialog_context: История диалога.
        dialog_context_prompt: Инструкция для контекста диалога.

    Returns:
        Список сообщений [{"role": "system"/"user", "content": "..."}].
    """
    user_parts: list[str] = []

    if dialog_context and dialog_context.strip():
        ctx_header = dialog_context_prompt or "История диалога:"
        user_parts.append(f"{ctx_header}\n{dialog_context}")

    if search_context and search_context.strip():
        user_parts.append(f"Контекст из базы знаний:\n{search_context}")

    q = question
    if len(q) > QUESTION_MAX_CHARS:
        q = q[:QUESTION_MAX_CHARS]
    user_parts.append(f"Вопрос студента: {q}")

    user_content = "\n\n".join(user_parts)

    total_chars = len(system_prompt) + len(user_content)
    logger.info(
        f"[PAYLOAD] Sections: "
        f"dialog_context={bool(dialog_context)}, "
        f"search_context={bool(search_context)}, "
        f"user_content_len={len(user_content)}, "
        f"total_chars={total_chars}, "
        f"estimated_tokens={total_chars // 4}"
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
) -> list[dict]:
    """Сформировать messages для случая без контекста поиска.

    Args:
        system_prompt: Системный промт (SYSTEM_PROMPT_NO_CONTEXT).
        question: Вопрос пользователя.
        dialog_context: История диалога.
        dialog_context_prompt: Инструкция для контекста диалога.

    Returns:
        Список сообщений [{"role": "system"/"user", "content": "..."}].
    """
    user_parts: list[str] = []

    if dialog_context and dialog_context.strip():
        ctx_header = dialog_context_prompt or "История диалога:"
        user_parts.append(f"{ctx_header}\n{dialog_context}")

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
