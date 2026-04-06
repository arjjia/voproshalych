"""Тесты векторного поиска по чанкам."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import qa.kb.search as kb_search


class _FakeConnection:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows
        self.statement = ""
        self.params: dict[str, object] = {}

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return self._rows


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def connect(self) -> _FakeConnection:
        return self._connection


@pytest.mark.asyncio
async def test_search_chunks_uses_configured_similarity_threshold() -> None:
    """Поиск должен прокидывать порог similarity из KB-конфига в SQL."""
    connection = _FakeConnection(
        [
            SimpleNamespace(
                id=1,
                text="Текст",
                title="Документ",
                source_url="https://example.org/doc",
                similarity=0.42,
            )
        ]
    )

    with patch(
        "qa.kb.search.get_engine",
        return_value=_FakeEngine(connection),
    ), patch(
        "qa.kb.search.get_kb_config",
        return_value=SimpleNamespace(search_similarity_threshold=0.5),
    ):
        chunks = await kb_search.search_chunks(
            query="Как закрыть физру?",
            embedding=[0.1, 0.2, 0.3],
            top_k=3,
        )

    assert len(chunks) == 1
    assert chunks[0]["similarity"] == pytest.approx(0.42)
    assert "max_similarity" in connection.params
    assert connection.params["max_similarity"] == pytest.approx(0.5)
    assert "<= :max_similarity" in connection.statement


@pytest.mark.asyncio
async def test_search_chunks_allows_overriding_similarity_threshold() -> None:
    """Явный threshold в вызове должен иметь приоритет над конфигом."""
    connection = _FakeConnection([])

    with patch(
        "qa.kb.search.get_engine",
        return_value=_FakeEngine(connection),
    ), patch(
        "qa.kb.search.get_kb_config",
        return_value=SimpleNamespace(search_similarity_threshold=0.5),
    ):
        await kb_search.search_chunks(
            query="Пожарная безопасность",
            embedding=[0.1, 0.2, 0.3],
            top_k=3,
            max_similarity=0.35,
        )

    assert connection.params["max_similarity"] == pytest.approx(0.35)
