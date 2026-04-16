"""Unit тесты для провайдеров LLM."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from qa.llm.providers.base import LLMResponse
from qa.llm.providers.mistral import MistralProvider
from qa.llm.providers.openrouter import OpenRouterProvider
from qa.llm.providers.gigachat import GigaChatProvider


class TestMistralProvider:
    """Тесты для MistralProvider."""

    def test_init(self):
        """Тест инициализации."""
        provider = MistralProvider(api_key="test-key")

        assert provider.name == "mistral"
        assert provider._api_key == "test-key"
        assert provider._model == "open-mistral-nemo"

    def test_is_available_with_key(self):
        """Тест доступности с ключом."""
        provider = MistralProvider(api_key="test-key")

        assert provider.is_available() is True

    def test_is_available_without_key(self):
        """Тест доступности без ключа."""
        provider = MistralProvider(api_key="")

        assert provider.is_available() is False


class TestOpenRouterProvider:
    """Тесты для OpenRouterProvider."""

    def test_init(self):
        """Тест инициализации."""
        provider = OpenRouterProvider(api_key="test-key")

        assert provider.name == "openrouter"
        assert provider._api_key == "test-key"
        assert len(provider._models) > 0

    def test_is_available_with_key(self):
        """Тест доступности с ключом."""
        provider = OpenRouterProvider(api_key="test-key")

        assert provider.is_available() is True

    def test_is_available_without_key(self):
        """Тест доступности без ключа."""
        provider = OpenRouterProvider(api_key="")

        assert provider.is_available() is False


class TestGigaChatProvider:
    """Тесты для GigaChatProvider."""

    def test_init(self):
        """Тест инициализации."""
        provider = GigaChatProvider(
            client_id="test-id",
            client_secret="test-secret",
        )

        assert provider.name == "gigachat"
        assert provider._auth_key is not None
        assert provider._model == "GigaChat"

    def test_is_available_with_credentials(self):
        """Тест доступности с креденшилами."""
        provider = GigaChatProvider(
            client_id="test-id",
            client_secret="test-secret",
        )

        assert provider.is_available() is True
        assert provider._auth_key is not None

    def test_is_available_without_client_id(self):
        """Тест доступности без client_id."""
        provider = GigaChatProvider(
            client_id="",
            client_secret="test-secret",
        )

        assert provider.is_available() is False

    def test_is_available_without_client_secret(self):
        """Тест доступности без client_secret."""
        provider = GigaChatProvider(
            client_id="test-id",
            client_secret="",
        )

        assert provider.is_available() is False

    def test_is_available_without_credentials(self):
        """Тест доступности без креденшилов."""
        provider = GigaChatProvider(
            client_id="",
            client_secret="",
        )

        assert provider.is_available() is False


class TestLLMResponse:
    """Тесты для LLMResponse."""

    def test_create_response(self):
        """Тест создания ответа."""
        response = LLMResponse(
            content="Test response",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

        assert response.content == "Test response"
        assert response.model == "test-model"
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 5
