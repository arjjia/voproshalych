"""OpenRouter провайдер."""

import logging
import time

import httpx

from .base import BaseLLMProvider, LLMResponse
from ..config import get_llm_config

logger = logging.getLogger(__name__)

RETRY_STATUS_CODES = (429, 502, 503, 504, 408)
NO_RETRY_STATUS_CODES = (400, 401, 402, 403)


def _get_timeout_for_model(model: str, config) -> float:
    """Получить таймаут для конкретной модели.

    Args:
        model: Идентификатор модели
        config: Конфигурация LLM

    Returns:
        Таймаут в секундах
    """
    model_lower = model.lower()

    if "nemotron" in model_lower:
        return float(config.nemotron_timeout)
    elif "qwen" in model_lower:
        return float(config.qwen_timeout)
    elif "openrouter/free" in model_lower:
        return 120.0
    else:
        return 60.0


async def _retry_with_backoff(
    func,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
):
    """Выполнить запрос с retry и экспоненциальным backoff.

    Args:
        func: Асинхронная функция для выполнения
        max_retries: Максимальное количество попыток
        backoff_factor: Коэффициент backoff

    Returns:
        Результат выполнения функции

    Raises:
        Exception: Последняя ошибка после исчерпания попыток
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await func()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code

            if status_code in NO_RETRY_STATUS_CODES:
                raise

            last_error = e
            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2 ** attempt)
                logger.warning(
                    f"HTTP {status_code}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                )
                import asyncio

                await asyncio.sleep(wait_time)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2 ** attempt)
                logger.warning(
                    f"Error: {e}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                )
                import asyncio

                await asyncio.sleep(wait_time)

    raise last_error


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

    async def health_check(self, model: str | None = None) -> dict:
        """Проверить доступность и здоровье OpenRouter API для конкретной модели.

        Args:
            model: Модель для проверки (по умолчанию первая из списка)

        Returns:
            dict с ключами:
                - status: 'ok' | 'error' | 'unavailable'
                - message: описание результата
                - latency_ms: время отклика в миллисекундах
                - error: детали ошибки если есть
        """
        if not self._api_key:
            return {"status": "unavailable", "message": "No API key configured", "latency_ms": 0, "error": None}

        check_model = model or self._models[0] if self._models else self._fallback_model

        try:
            start_time = time.time()
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://voproshalych.utmn.ru",
                        "X-Title": "Voproshalych",
                    },
                    json={
                        "model": check_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                )
                latency_ms = int((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    return {"status": "ok", "message": f"OpenRouter ({check_model}) is accessible", "latency_ms": latency_ms, "error": None}
                elif response.status_code == 401:
                    return {"status": "unavailable", "message": "Invalid API key", "latency_ms": latency_ms, "error": "401 Unauthorized"}
                else:
                    return {"status": "error", "message": f"HTTP {response.status_code}", "latency_ms": latency_ms, "error": response.text[:200]}

        except httpx.ConnectError as e:
            return {"status": "unavailable", "message": "Connection failed", "latency_ms": 0, "error": str(e)}
        except httpx.TimeoutException:
            return {"status": "error", "message": "Request timeout", "latency_ms": 15000, "error": "Timeout"}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {e}", "latency_ms": 0, "error": str(e)}

    async def _call_api(
        self,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        messages: list[dict] | None = None,
    ) -> LLMResponse:
        """Вызвать OpenRouter API с конкретной моделью.

        Args:
            model: Модель для использования
            prompt: Промпт для LLM (fallback если messages is None)
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов
            messages: Список сообщений ChatCompletion (приоритет над prompt)

        Returns:
            LLMResponse с ответом

        Raises:
            httpx.HTTPStatusError: При ошибке API
        """
        config = get_llm_config()
        timeout = _get_timeout_for_model(model, config)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://voproshalych.utmn.ru",
            "X-Title": "Voproshalych",
        }

        api_messages = messages if messages else [{"role": "user", "content": prompt}]

        payload = {
            "model": model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        backoff_factor = 1.0 if "qwen" not in model.lower() else 2.0

        async def _make_request():
            async with httpx.AsyncClient(timeout=timeout) as client:
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

        return await _retry_with_backoff(_make_request, max_retries=3, backoff_factor=backoff_factor)

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        messages: list[dict] | None = None,
    ) -> LLMResponse:
        """Генерировать ответ через OpenRouter API с fallback логикой.

        Сначала пробует модели по порядку из списка. Если все не работают -
        пробует fallback модель (openrouter/free).

        Args:
            prompt: Промпт для LLM (fallback если messages is None)
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов
            messages: Список сообщений ChatCompletion (приоритет над prompt)

        Returns:
            LLMResponse с ответом

        Raises:
            Exception: Если все модели не работают
        """
        last_error: Exception | None = None

        for model in self._models:
            try:
                logger.debug(f"OpenRouter: trying model {model}")
                return await self._call_api(model, prompt, temperature, max_tokens, messages)
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
                    self._fallback_model, prompt, temperature, max_tokens, messages
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
