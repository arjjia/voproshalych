"""Mistral AI провайдер."""

import logging

import httpx

from .base import BaseLLMProvider, LLMResponse
from ..config import get_llm_config

logger = logging.getLogger(__name__)

RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
NO_RETRY_STATUS_CODES = (400, 401, 403)


class MistralProvider(BaseLLMProvider):
    """Провайдер Mistral AI.

    Attributes:
        api_key: API ключ Mistral
        model: Модель для использования
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Инициализировать провайдер.

        Args:
            api_key: API ключ (опционально, берется из конфига)
            model: Модель (опционально, берется из конфига)
        """
        config = get_llm_config()
        self._api_key = api_key or config.mistral_api_key
        self._model = model or config.mistral_model

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "mistral"

    def is_available(self) -> bool:
        """Проверить доступность провайдера."""
        return bool(self._api_key)

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Генерировать ответ через Mistral API.

        Args:
            prompt: Промпт для LLM
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов

        Returns:
            LLMResponse с ответом

        Raises:
            httpx.HTTPStatusError: При ошибке API
        """
        config = get_llm_config()
        timeout = float(config.mistral_timeout)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        backoff_factor = 2.0

        async def _make_request():
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://api.mistral.ai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()

                data = response.json()

                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=self._model,
                    usage={
                        "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                        "completion_tokens": data.get("usage", {}).get(
                            "completion_tokens", 0
                        ),
                        "total_tokens": data.get("usage", {}).get("total_tokens", 0),
                    },
                )

        last_error = None

        for attempt in range(3):
            try:
                return await _make_request()
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code in NO_RETRY_STATUS_CODES:
                    raise

                last_error = e
                if attempt < 2:
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"Mistral HTTP {status_code}, retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    import asyncio

                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"Mistral error: {e}, retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    import asyncio

                    await asyncio.sleep(wait_time)

        raise last_error
