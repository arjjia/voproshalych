"""Mistral AI провайдер."""

import asyncio
import logging
import time

import requests

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
                    timeout=15,
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
            },
            json=payload,
            timeout=timeout,
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

        logger.info(f"Mistral request: model={self._model}, prompt_len={len(prompt)} chars, messages={len(api_messages)}, timeout={timeout}s")

        last_error = None

        for attempt in range(3):
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
                last_error = e
                if attempt < 2:
                    wait_time = 2.0 * (2 ** attempt)
                    logger.warning(f"Mistral HTTP {status_code}, retrying in {wait_time}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2.0 * (2 ** attempt)
                    logger.warning(f"Mistral error: {e}, retrying in {wait_time}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(wait_time)

        raise last_error
