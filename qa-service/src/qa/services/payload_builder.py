"""Формирование и адаптивное сокращение payload для LLM."""

import logging

logger = logging.getLogger(__name__)

MAX_PROMPT_TOKENS = 2000
CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Оценить количество токенов в тексте (грубая оценка: 1 токен ≈ 4 символа)."""
    return len(text) // CHARS_PER_TOKEN


def build_messages(
    system_prompt: str,
    question: str,
    search_context: str | None = None,
    dialog_context: str | None = None,
    dialog_context_prompt: str | None = None,
) -> list[dict]:
    """Сформировать messages[] для ChatCompletion API с адаптивным сокращением.

    Приоритет сохранения (что отбрасываем последним):
    1. system_prompt — обязателен
    2. question — обязателен
    3. search_context — важен для ответа
    4. dialog_context — наименее важен, отбрасываем первым

    Args:
        system_prompt: Системный промт.
        question: Вопрос пользователя.
        search_context: Контекст из поиска (чанки, entities).
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

    user_parts.append(f"Вопрос студента: {question}")

    user_content = "\n\n".join(user_parts)
    total_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_content)

    strategy = "full"
    if total_tokens > MAX_PROMPT_TOKENS:
        logger.warning(
            f"[PAYLOAD] Total ~{total_tokens} tokens > {MAX_PROMPT_TOKENS} limit, "
            f"truncating..."
        )

        if dialog_context and dialog_context.strip():
            user_parts_no_ctx = [
                f"Контекст из базы знаний:\n{search_context}"
                if search_context
                else None,
                f"Вопрос студента: {question}",
            ]
            user_parts_no_ctx = [p for p in user_parts_no_ctx if p]
            user_content_no_ctx = "\n\n".join(user_parts_no_ctx)
            tokens_no_ctx = _estimate_tokens(system_prompt) + _estimate_tokens(
                user_content_no_ctx
            )

            if tokens_no_ctx <= MAX_PROMPT_TOKENS:
                user_content = user_content_no_ctx
                strategy = "no_dialog_context"
                logger.info("[PAYLOAD] Removed dialog context, fits in limit")
            else:
                truncated_search = _truncate_search_context(
                    search_context or "", MAX_PROMPT_TOKENS - _estimate_tokens(system_prompt) - _estimate_tokens(question) - 50
                )
                user_content = f"Контекст из базы знаний:\n{truncated_search}\n\nВопрос студента: {question}"
                strategy = "truncated_search"
                logger.info("[PAYLOAD] Removed dialog context + truncated search")
        else:
            truncated_search = _truncate_search_context(
                search_context or "", MAX_PROMPT_TOKENS - _estimate_tokens(system_prompt) - _estimate_tokens(question) - 50
            )
            user_content = f"Контекст из базы знаний:\n{truncated_search}\n\nВопрос студента: {question}"
            strategy = "truncated_search"

    final_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_content)
    logger.info(
        f"[PAYLOAD] Strategy: {strategy}, "
        f"estimated tokens: system={_estimate_tokens(system_prompt)}, "
        f"user={_estimate_tokens(user_content)}, total={final_tokens}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _truncate_search_context(search_context: str, max_tokens: int) -> str:
    """Обрезать контекст поиска до лимита токенов.

    Args:
        search_context: Полный контекст поиска.
        max_tokens: Максимум токенов.

    Returns:
        Обрезанный контекст.
    """
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(search_context) <= max_chars:
        return search_context

    truncated = search_context[:max_chars]
    last_boundary = truncated.rfind("\n---\n")
    if last_boundary > max_chars * 0.5:
        truncated = truncated[:last_boundary]

    return truncated.strip() + "\n\n[... часть контекста опущена ...]"
