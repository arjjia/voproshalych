"""Тесты QAServiceClient для одиночных запросов без неявных ретраев."""

from unittest.mock import MagicMock

import httpx

from services.qa_service_client import (
    QAServiceClient,
    QAServiceError,
    QAServiceRateLimited,
    QAServiceTimeout,
)


def test_ask_returns_answer_from_single_request() -> None:
    """Успешный ответ должен возвращаться без дополнительных вызовов."""
    client = QAServiceClient(base_url="http://qa-service", timeout_seconds=10)
    client._client = MagicMock()
    client._client.post.return_value = httpx.Response(
        200,
        request=httpx.Request("POST", "http://qa-service/qa"),
        json={
            "answer": "Ответ",
            "expanded_query": "Расширенный запрос",
            "keywords": {"high_level": ["тест"], "low_level": ["вопрос"]},
            "model": "lightrag-mix",
        },
    )

    result = client.ask("Вопрос", context="Контекст")

    assert result["answer"] == "Ответ"
    assert result["expanded_query"] == "Расширенный запрос"
    assert result["keywords"] == {"high_level": ["тест"], "low_level": ["вопрос"]}
    client._client.post.assert_called_once_with(
        "/qa",
        json={"question": "Вопрос", "context": "Контекст"},
    )


def test_ask_does_not_retry_on_server_error() -> None:
    """Даже при 5xx должен быть только один downstream-запрос."""
    client = QAServiceClient(base_url="http://qa-service", timeout_seconds=10)
    client._client = MagicMock()
    client._client.post.return_value = httpx.Response(
        500,
        request=httpx.Request("POST", "http://qa-service/qa"),
        text="internal error",
    )

    try:
        client.ask("Вопрос")
    except QAServiceError as exc:
        assert str(exc) == "QA service error: 500"
    else:
        raise AssertionError("QAServiceError was not raised")

    client._client.post.assert_called_once()


def test_ask_does_not_retry_on_rate_limit() -> None:
    """Rate limit должен завершать запрос без повторных попыток."""
    client = QAServiceClient(base_url="http://qa-service", timeout_seconds=10)
    client._client = MagicMock()
    client._client.post.return_value = httpx.Response(
        429,
        request=httpx.Request("POST", "http://qa-service/qa"),
        text="too many requests",
    )

    try:
        client.ask("Вопрос")
    except QAServiceRateLimited as exc:
        assert str(exc) == "QA service rate limited"
    else:
        raise AssertionError("QAServiceRateLimited was not raised")

    client._client.post.assert_called_once()


def test_ask_does_not_retry_on_timeout() -> None:
    """Timeout не должен порождать дополнительные попытки POST /qa."""
    client = QAServiceClient(base_url="http://qa-service", timeout_seconds=10)
    client._client = MagicMock()
    client._client.post.side_effect = httpx.TimeoutException("timeout")

    try:
        client.ask("Вопрос")
    except QAServiceTimeout as exc:
        assert str(exc) == "QA service timeout"
    else:
        raise AssertionError("QAServiceTimeout was not raised")

    client._client.post.assert_called_once()
