"""Тесты клиента qa-service."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_qa_client_ask_success(httpx_mock):
    """Проверяет успешный запрос к qa-service."""
    from src.kb.qa_client import QAServiceClient

    httpx_mock.add_response(
        url="http://test:8004/qa",
        method="POST",
        json={
            "answer": "Тестовый ответ.",
            "source_links": [{"title": "Источник", "url": "https://example.com"}],
            "question_type": 1,
        },
    )

    client = QAServiceClient("http://test:8004")
    result = await client.ask("тестовый вопрос")

    assert result is not None
    assert result["answer"] == "Тестовый ответ."
    assert len(result["sources"]) == 1


@pytest.mark.asyncio
async def test_qa_client_empty_answer(httpx_mock):
    """Проверяет пустой ответ."""
    from src.kb.qa_client import QAServiceClient

    httpx_mock.add_response(
        url="http://test:8004/qa",
        method="POST",
        json={"answer": ""},
    )

    client = QAServiceClient("http://test:8004")
    result = await client.ask("test")
    assert result is None


@pytest.mark.asyncio
async def test_qa_client_timeout():
    """Проверяет таймаут."""
    from src.kb.qa_client import QAServiceClient

    client = QAServiceClient("http://test:8004", timeout=1)

    # Let the real timeout happen by pointing to nonexistent host
    # This tests the timeout exception handling
    result = await client.ask("test")
    assert result is not None
    # Should get either timeout or error message
    assert result.get("answer")


@pytest.mark.asyncio
async def test_qa_client_http_error(httpx_mock):
    """Проверяет HTTP-ошибку."""
    from src.kb.qa_client import QAServiceClient

    httpx_mock.add_response(
        url="http://test:8004/qa",
        method="POST",
        status_code=503,
    )

    client = QAServiceClient("http://test:8004")
    result = await client.ask("test")
    assert result is not None
    assert "недоступен" in result.get("answer", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
