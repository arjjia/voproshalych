"""Тесты SSE streaming."""

import pytest

from src.models import AgentState, Intent, Complexity


@pytest.mark.asyncio
async def test_stream_agent_events():
    """Проверяет формат SSE-событий."""
    from src.streaming import stream_agent_events

    state = AgentState(
        messages=[{"role": "user", "content": "test"}],
        intent=Intent.KB_QA,
        complexity=Complexity.SIMPLE,
        final_answer="Тестовый ответ.",
        sources=[{"title": "Источник", "url": "https://example.com"}],
    )

    events = []
    async for event in stream_agent_events(state):
        events.append(event)

    assert len(events) >= 4

    assert "event: event" in events[0]
    assert "agent_start" in events[0]

    assert any("event: done" in e for e in events)

    has_answer = any("Тестовый ответ" in e for e in events)
    assert has_answer, "Ответ должен быть в SSE событиях"

    has_source = any("Источник" in e for e in events)
    assert has_source, "Источники должны быть в SSE событиях"


@pytest.mark.asyncio
async def test_stream_no_sources():
    """Проверяет SSE без источников."""
    from src.streaming import stream_agent_events

    state = AgentState(
        messages=[],
        final_answer="Ответ без источников.",
        sources=[],
    )

    events = []
    async for event in stream_agent_events(state):
        events.append(event)

    has_done = any("event: done" in e for e in events)
    assert has_done


@pytest.mark.asyncio
async def test_stream_error():
    """Проверяет SSE с ошибкой."""
    from src.streaming import stream_agent_events

    state = AgentState(
        messages=[],
        error="Test error",
        final_answer=None,
    )

    events = []
    async for event in stream_agent_events(state):
        events.append(event)

    has_error = any("event: error" in e for e in events)
    assert has_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
