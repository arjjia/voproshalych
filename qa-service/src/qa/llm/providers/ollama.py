"""Ollama провайдер для локальных LLM моделей."""

import asyncio
import logging
import os
import time

import requests

from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Провайдер для Ollama (локальные модели).

    Использует OpenAI-совместимый API Ollama.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model or os.getenv("OLLAMA_MODEL", "gemma4:e4b")
        self._base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self._api_url = f"{self._base_url}/v1/chat/completions"
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        return bool(self._model)

    async def health_check(self) -> dict:
        try:
            start_time = time.time()

            def _ping():
                return self._session.get(
                    f"{self._base_url}/api/tags",
                    timeout=5,
                )

            response = await asyncio.to_thread(_ping)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                models = [
                    m.get("name", "")
                    for m in response.json().get("models", [])
                ]
                model_found = any(self._model in m for m in models)
                if model_found:
                    return {
                        "status": "ok",
                        "message": f"Ollama {self._model} ready",
                        "latency_ms": latency_ms,
                        "error": None,
                    }
                return {
                    "status": "error",
                    "message": f"Model {self._model} not found. Available: {models[:5]}",
                    "latency_ms": latency_ms,
                    "error": None,
                }
            return {
                "status": "error",
                "message": f"HTTP {response.status_code}",
                "latency_ms": latency_ms,
                "error": response.text[:200],
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "message": str(e),
                "latency_ms": 0,
                "error": str(e),
            }

    def _sync_generate(self, payload: dict, timeout: float) -> dict:
        response = self._session.post(
            self._api_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    async def generate(
        self,
        prompt: str,
        temperature: float = 1.0,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        logger.info(
            f"Ollama request: model={self._model}, "
            f"prompt_len={len(prompt)} chars"
        )

        last_error = None

        for attempt in range(3):
            try:
                data = await asyncio.to_thread(
                    self._sync_generate, payload, 300.0
                )
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return LLMResponse(
                    content=content,
                    model=self._model,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                )
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 0
                if status_code in (400, 401, 403, 404):
                    raise
                last_error = e
                if attempt < 2:
                    wait_time = 2.0 * (2 ** attempt)
                    logger.warning(
                        f"Ollama HTTP {status_code}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2.0 * (2 ** attempt)
                    logger.warning(
                        f"Ollama error: {e}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait_time)

        raise last_error
