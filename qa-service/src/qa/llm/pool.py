"""LLM Pool - управление провайдерами с fallback."""

import logging
from typing import Any

from .providers.base import BaseLLMProvider, LLMResponse
from .providers import MistralProvider, OpenRouterProvider, GigaChatProvider
from .config import get_llm_config, LLMConfig

logger = logging.getLogger(__name__)


class LLMPool:
    """Пул LLM провайдеров с fallback логикой.

    Attributes:
        providers: Словарь провайдеров
        priority: Список провайдеров по приоритету
        config: Конфигурация LLM
    """

    def __init__(self, config: LLMConfig | None = None):
        """Инициализировать пул.

        Args:
            config: Конфигурация LLM (опционально)
        """
        self._config = config or get_llm_config()
        self._providers: dict[str, BaseLLMProvider] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        """Инициализировать провайдеры."""
        self._providers = {
            "mistral": MistralProvider(api_key=self._config.mistral_api_key),
            "openrouter": OpenRouterProvider(api_key=self._config.openrouter_api_key),
            "gigachat": GigaChatProvider(
                client_id=self._config.gigachat_client_id,
                client_secret=self._config.gigachat_client_secret,
            ),
        }
        logger.debug(f"LLM providers initialized: {list(self._providers.keys())}")

    def get_available_providers(self) -> list[str]:
        """Получить список доступных провайдеров.

        Returns:
            Список имен доступных провайдеров
        """
        return [
            name
            for name, provider in self._providers.items()
            if provider.is_available()
        ]

    def select_model(self) -> str | None:
        """Выбрать первую доступную модель по приоритету.

        Returns:
            Имя провайдера или None, если нет доступных
        """
        available = self.get_available_providers()
        for provider_name in self._config.model_priority:
            if provider_name in available:
                logger.debug(f"Selected provider: {provider_name}")
                return provider_name

        logger.warning("No available LLM providers")
        return None

    async def call(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        provider_name: str | None = None,
        messages: list[dict] | None = None,
    ) -> LLMResponse:
        """Вызвать LLM с fallback логикой.

        Args:
            prompt: Промпт для LLM (используется если messages is None)
            temperature: Температура генерации (по умолчанию из конфига)
            max_tokens: Максимальное количество токенов (по умолчанию из конфига)
            provider_name: Конкретный провайдер (опционально)
            messages: Список сообщений ChatCompletion (приоритет над prompt)

        Returns:
            LLMResponse с ответом

        Raises:
            ValueError: Если нет доступных провайдеров
        """
        temperature = temperature or self._config.default_temperature
        max_tokens = max_tokens or self._config.default_max_tokens

        if provider_name:
            providers_to_try = [provider_name]
        else:
            available = self.get_available_providers()
            providers_to_try = [
                p for p in self._config.model_priority if p in available
            ]

        if not providers_to_try:
            raise ValueError("No available LLM providers")

        last_error: Exception | None = None
        for prov_name in providers_to_try:
            provider = self._providers.get(prov_name)
            if not provider:
                logger.warning(f"Provider {prov_name} not found in pool")
                continue
            if not provider.is_available():
                logger.warning(f"Provider {prov_name} is not available")
                continue

            try:
                logger.debug(f"Calling provider: {prov_name}")
                response = await provider.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=messages,
                )
                logger.debug(
                    f"Provider {prov_name} succeeded, "
                    f"tokens: {response.usage}"
                )
                return response
            except Exception as e:
                logger.warning(f"Provider {prov_name} failed: {e}")
                last_error = e
                continue

        logger.error(f"All providers failed. Tried: {providers_to_try}")
        raise ValueError(f"All providers failed. Last error: {last_error}")

    async def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> LLMResponse:
        """Генерировать ответ (алиас для call).

        Args:
            prompt: Промпт для LLM
            **kwargs: Дополнительные параметры

        Returns:
            LLMResponse с ответом
        """
        return await self.call(prompt, **kwargs)


_llm_pool: LLMPool | None = None


def get_llm_pool() -> LLMPool:
    """Получить экземпляр LLM пула.

    Returns:
        LLMPool
    """
    global _llm_pool
    if _llm_pool is None:
        _llm_pool = LLMPool()
    return _llm_pool
