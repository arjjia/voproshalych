"""Mistral AI провайдер."""

import asyncio
import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import BaseLLMProvider, LLMResponse
from ..config import get_llm_config

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

NO_RETRY_STATUS_CODES = (400, 401, 403)


class MistralProvider(BaseLLMProvider):
    """Провайдер Mistral AI.

    Использует requests (синхронный) как в проверенной старой реализации voproshalych.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        config = get_llm_config()
        self._api_key = api_key or config.mistral_api_key
        self._model = model or config.mistral_model
        self._session = requests.Session()

        retry = Retry(
            total=3,
            backoff_factor=0.2,
            status_forcelist=[502, 503, 504, 429],
            allowed_methods=["POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=1,
            pool_maxsize=1,
        )
        self._session.mount("https://", adapter)

    async def warmup(self) -> None:
        """Прогреть соединение с Mistral API минимальным запросом."""
        if not self._api_key:
            return
        try:
            def _warmup():
                self._session.post(
                    MISTRAL_API_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    timeout=(5, 15),
                )

            await asyncio.to_thread(_warmup)
            logger.info("Mistral warmup done")
        except Exception as e:
            logger.warning(f"Mistral warmup failed (non-fatal): {e}")

    @property
    def name(self) -> str:
        return "mistral"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def health_check(self) -> dict:
        if not self._api_key:
            return {"status": "unavailable", "message": "No API key configured", "latency_ms": 0, "error": None}

        try:
            start_time = time.time()

            def _ping():
                return self._session.post(
                    MISTRAL_API_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    timeout=(5, 15),
                )

            response = await asyncio.to_thread(_ping)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return {"status": "ok", "message": "Mistral API is accessible", "latency_ms": latency_ms, "error": None}
            elif response.status_code == 401:
                return {"status": "unavailable", "message": "Invalid API key", "latency_ms": latency_ms, "error": "401 Unauthorized"}
            else:
                return {"status": "error", "message": f"HTTP {response.status_code}", "latency_ms": latency_ms, "error": response.text[:200]}

        except Exception as e:
            logger.error(f"Mistral health_check exception: {e}")
            return {"status": "error", "message": str(e), "latency_ms": 0, "error": str(e)}

    def _sync_generate(self, payload: dict, timeout: float) -> dict:
        response = self._session.post(
            MISTRAL_API_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "Connection": "close",
            },
            json=payload,
            timeout=(5, timeout),
        )
        response.raise_for_status()
        return response.json()

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        messages: list[dict] | None = None,
    ) -> LLMResponse:
        config = get_llm_config()
        timeout = float(config.mistral_timeout)

        api_messages = messages if messages else [{"role": "user", "content": prompt}]

        payload = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        total_chars = sum(len(m.get("content", "")) for m in api_messages)
        logger.debug(
            f"Mistral request: model={self._model}, total_chars={total_chars}, "
            f"messages={len(api_messages)}, timeout={timeout}s"
        )

        try:
            data = await asyncio.to_thread(self._sync_generate, payload, timeout)
            return LLMResponse(
                content=data["choices"][0]["message"]["content"],
                model=self._model,
                usage={
                    "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                    "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                    "total_tokens": data.get("usage", {}).get("total_tokens", 0),
                },
            )
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            if status_code in NO_RETRY_STATUS_CODES:
                raise
            logger.warning(f"Mistral HTTP error after adapter retries: {status_code}")
            raise
        except Exception as e:
            logger.warning(f"Mistral error after adapter retries: {e}")
            raise
