"""SSE streaming — отправка событий агента клиенту."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from .models import AgentState

logger = logging.getLogger(__name__)


async def stream_agent_events(
    state: AgentState,
) -> AsyncGenerator[str, None]:
    """Генерирует SSE-события по мере выполнения агента.

    Формат событий:
    - event: thought — мысль агента
    - event: tool_call — вызов инструмента
    - event: tool_result — результат инструмента
    - event: token — токен ответа
    - event: source — источник
    - event: done — завершение
    - event: error — ошибка
    """
    yield _sse("event", "agent_start")

    yield _sse("thought", {
        "type": "classification",
        "intent": state.intent.value if state.intent else "unknown",
        "complexity": state.complexity.value if state.complexity else "simple",
    })
    await asyncio.sleep(0.01)

    if state.intent and state.intent.value == "kb_qa":
        yield _sse("thought", {"type": "action", "text": "🔍 Ищу информацию в базе знаний ТюмГУ..."})
        await asyncio.sleep(0.01)

    elif state.intent and state.intent.value == "tool_required":
        yield _sse("thought", {"type": "action", "text": "🔄 Обращаюсь к сервисам университета..."})
        await asyncio.sleep(0.01)

    if state.error:
        yield _sse("error", {"message": state.error})
        await asyncio.sleep(0.01)

    if state.final_answer:
        yield _sse("token", {"text": state.final_answer})
        await asyncio.sleep(0.01)

    if state.sources:
        for source in state.sources:
            yield _sse("source", source)
            await asyncio.sleep(0.01)

    yield _sse("done", {})


def _sse(event: str, data: dict | str) -> str:
    """Форматирует SSE-сообщение."""
    data_str = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {data_str}\n\n"
