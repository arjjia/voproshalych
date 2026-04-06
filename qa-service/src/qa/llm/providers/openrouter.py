"""OpenRouter провайдер."""

import logging

import httpx

from .base import BaseLLMProvider, LLMResponse
from ..config import get_llm_config

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseLLMProvider):
    """Провайдер OpenRouter.

    Attributes:
        api_key: API ключ OpenRouter
        models: Список моделей по приоритету (от лучшего к худшему)
        fallback_model: Модель для случайного выбора (резервная)
    """

    def __init__(
        self,
        api_key: str | None = None,
        models: list[str] | None = None,
        fallback_model: str | None = None,
    ):
        """Инициализировать провайдер.

        Args:
            api_key: API ключ (опционально, берется из конфига)
            models: Список моделей (опционально, берется из конфига)
            fallback_model: Резервная модель (опционально, берется из конфига)
        """
        config = get_llm_config()
        self._api_key = api_key or config.openrouter_api_key
        self._models = models or config.openrouter_models
        self._fallback_model = fallback_model or config.openrouter_fallback_model

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "openrouter"

    def is_available(self) -> bool:
        """Проверить доступность провайдера."""
        return bool(self._api_key)

    async def _call_api(
        self, model: str, prompt: str, temperature: float, max_tokens: int
    ) -> LLMResponse:
        """Вызвать OpenRouter API с конкретной моделью.

        Args:
            model: Модель для использования
            prompt: Промпт для LLM
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов

        Returns:
            LLMResponse с ответом

        Raises:
            httpx.HTTPStatusError: При ошибке API
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://voproshalych.utmn.ru",
            "X-Title": "Voproshalych",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

            data = response.json()

            return LLMResponse(
                content=data["choices"][0]["message"]["content"],
                model=data.get("model", model),
                usage={
                    "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                    "completion_tokens": data.get("usage", {}).get(
                        "completion_tokens", 0
                    ),
                    "total_tokens": data.get("usage", {}).get("total_tokens", 0),
                },
            )

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Генерировать ответ через OpenRouter API с fallback логикой.

        Сначала пробует модели по порядку из списка. Если все не работают -
        пробует fallback модель (openrouter/free).

        Args:
            prompt: Промпт для LLM
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов

        Returns:
            LLMResponse с ответом

        Raises:
            Exception: Если все модели не работают
        """
        last_error: Exception | None = None

        for model in self._models:
            try:
                logger.debug(f"OpenRouter: trying model {model}")
                return await self._call_api(model, prompt, temperature, max_tokens)
            except Exception as e:
                logger.warning(f"OpenRouter model {model} failed: {e}")
                last_error = e
                continue

        if self._fallback_model:
            try:
                logger.debug(
                    f"OpenRouter: trying fallback model {self._fallback_model}"
                )
                return await self._call_api(
                    self._fallback_model, prompt, temperature, max_tokens
                )
            except Exception as e:
                logger.warning(
                    f"OpenRouter fallback model {self._fallback_model} failed: {e}"
                )
                last_error = e

        logger.error(
            f"All OpenRouter models failed. Tried: {self._models + [self._fallback_model]}"
        )
        raise Exception(f"All OpenRouter models failed. Last error: {last_error}")
