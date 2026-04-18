"""GigaChat провайдер с использованием официального SDK."""

import asyncio
import base64
import logging

from gigachat import GigaChat, ChatCompletion

from .base import BaseLLMProvider, LLMResponse
from ..config import get_llm_config

logger = logging.getLogger(__name__)

RETRY_ERROR_CODES = (429, 500, 502, 503, 504)
REAUTH_ERROR_CODES = (401, 403)


class GigaChatProvider(BaseLLMProvider):
    """Провайдер GigaChat (Сбер) через официальный SDK.

    Attributes:
        client_id: Client ID GigaChat
        client_secret: Client Secret GigaChat
        model: Модель для использования

    Особенности:
        - Freemium: 1 поток (concurrency=1), 1M токенов/год
        - OAuth токен валиден 30 минут, SDK управляет автоматически
        - SDK имеет встроенный retry, но добавляем дополнительную логику
    """

    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        """Инициализировать провайдер.

        Args:
            client_id: Client ID (опционально, берется из конфига)
            client_secret: Client Secret (опционально, берется из конфига)
        """
        config = get_llm_config()
        client_id = client_id or config.gigachat_client_id
        client_secret = client_secret or config.gigachat_client_secret
        self._auth_key = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        self._scope = "GIGACHAT_API_PERS"
        self._model = "GigaChat"
        self._client: GigaChat | None = None
        self._timeout = float(config.gigachat_timeout)

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "gigachat"

    def is_available(self) -> bool:
        """Проверить доступность провайдера."""
        return bool(self._auth_key and self._auth_key != ":")

    async def health_check(self) -> dict:
        """Проверить доступность и здоровье GigaChat API.

        Returns:
            dict с ключами:
                - status: 'ok' | 'error' | 'unavailable'
                - message: описание результата
                - latency_ms: время отклика в миллисекундах
                - error: детали ошибки если есть
        """
        if not self._auth_key or self._auth_key == ":":
            return {"status": "unavailable", "message": "No credentials configured", "latency_ms": 0, "error": None}

        import time
        try:
            start_time = time.time()
            client = self._get_client()

            def _sync_health():
                return client.chat(
                    {
                        "messages": [{"role": "user", "content": "ping"}],
                        "temperature": 0.7,
                        "max_tokens": 1,
                    }
                )

            result = await asyncio.get_event_loop().run_in_executor(None, _sync_health)
            latency_ms = int((time.time() - start_time) * 1000)

            if result and result.choices:
                return {"status": "ok", "message": "GigaChat API is accessible", "latency_ms": latency_ms, "error": None}
            else:
                return {"status": "error", "message": "Empty response", "latency_ms": latency_ms, "error": "No choices in response"}

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000) if start_time else 0
            error_msg = str(e)
            if "credentials" in error_msg.lower() or "auth" in error_msg.lower():
                return {"status": "unavailable", "message": "Authentication failed", "latency_ms": latency_ms, "error": error_msg}
            return {"status": "error", "message": f"Request failed: {e}", "latency_ms": latency_ms, "error": error_msg}

    def _get_client(self) -> GigaChat:
        """Получить или создать клиент GigaChat.

        Returns:
            Клиент GigaChat
        """
        if self._client is None:
            self._client = GigaChat(
                credentials=self._auth_key,
                scope=self._scope,
                verify_ssl_certs=False,
                timeout=self._timeout,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Генерировать ответ через GigaChat API.

        Args:
            prompt: Промпт для LLM
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов

        Returns:
            LLMResponse с ответом

        Raises:
            Exception: При ошибке API
        """
        logger.info(f"GigaChat request: prompt_len={len(prompt)} chars, timeout={self._timeout}s")
        backoff_factor = 0.5

        async def _make_request():
            client = self._get_client()

            def _sync_chat():
                return client.chat(
                    {
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                )

            response: ChatCompletion = await asyncio.to_thread(_sync_chat)

            content = response.choices[0].message.content

            return LLMResponse(
                content=content,
                model=self._model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens
                    if response.usage
                    else 0,
                    "completion_tokens": response.usage.completion_tokens
                    if response.usage
                    else 0,
                    "total_tokens": response.usage.total_tokens
                    if response.usage
                    else 0,
                },
            )

        last_error = None

        for attempt in range(3):
            try:
                return await _make_request()
            except Exception as e:
                error_str = str(e).lower()
                last_error = e

                is_reauth_error = any(code in str(e) for code in REAUTH_ERROR_CODES)
                is_retryable = any(code in error_str for code in RETRY_ERROR_CODES)

                if is_reauth_error:
                    logger.warning(f"GigaChat auth error, recreating client: {e}")
                    self._client = None
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    raise

                if is_retryable and attempt < 2:
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"GigaChat retryable error: {e}, retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if attempt < 2:
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"GigaChat error: {e}, retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait_time)
                    continue

        logger.error(f"GigaChat failed after 3 attempts: {last_error}")
        raise last_error
