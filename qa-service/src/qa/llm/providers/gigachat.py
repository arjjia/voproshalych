"""GigaChat провайдер с использованием официального SDK."""

import base64
import logging

from gigachat import GigaChat, ChatCompletion

from .base import BaseLLMProvider, LLMResponse
from ..config import get_llm_config


logger = logging.getLogger(__name__)


class GigaChatProvider(BaseLLMProvider):
    """Провайдер GigaChat (Сбер) через официальный SDK.

    Attributes:
        client_id: Client ID GigaChat
        client_secret: Client Secret GigaChat
        model: Модель для использования
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

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "gigachat"

    def is_available(self) -> bool:
        """Проверить доступность провайдера."""
        return bool(self._auth_key)

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
        import asyncio

        try:
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

        except Exception as e:
            logger.error(f"GigaChat API error: {e}")
            raise
