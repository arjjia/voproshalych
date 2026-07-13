"""Тесты реестра инструментов kb-service (TOOLS/TOOL_FUNCTIONS/execute_tool)."""

import pytest

import kb.tools as tools_mod
from kb.tools import TOOL_FUNCTIONS, execute_tool


def test_news_and_events_tools_registered():
    """crawl_utmn_news и crawl_utmn_events должны быть в реестре."""
    assert "crawl_utmn_news" in TOOL_FUNCTIONS
    assert "crawl_utmn_events" in TOOL_FUNCTIONS


def test_classic_tools_still_registered():
    """Существовавшие инструменты не должны пропасть."""
    for name in (
        "kb_search",
        "kb_search_classified",
        "crawl_confluence_help",
        "crawl_confluence_study",
    ):
        assert name in TOOL_FUNCTIONS, f"{name} пропал из реестра"


@pytest.mark.asyncio
async def test_execute_tool_unknown_raises():
    with pytest.raises(ValueError):
        await execute_tool("definitely_unknown_tool_xyz", {})


def test_news_tool_functions_callable():
    assert callable(TOOL_FUNCTIONS["crawl_utmn_news"])
    assert callable(TOOL_FUNCTIONS["crawl_utmn_events"])
