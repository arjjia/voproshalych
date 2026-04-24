"""Ollama провайдер для LLM моделей через нативный API."""

import asyncio
import logging
import os
import time

import requests

from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Провайдер для Ollama.

    Использует нативный /api/chat endpoint для корректной работы
    с моделями, имеющими thinking mode (qwen3.6 и др.).
    Параметр think=False отключает reasoning и возвращает
    контент напрямую в message.content.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model or os.getenv("OLLAMA_MODEL", "qwen3.6:35b")
        self._base_url = (
            base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self._api_url = f"{self._base_url}/api/chat"
        self._api_key = os.getenv("OLLAMA_API_KEY", "")
        self._session = requests.Session()
        if self._api_key:
            self._session.headers.update({"Authorization": f"Bearer {self._api_key}"})
        logger.info(
            "Ollama provider initialized: base_url=%s model=%s auth=%s",
            self._base_url,
            self._model,
            "set" if self._api_key else "empty",
        )

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
                models = [m.get("name", "") for m in response.json().get("models", [])]
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
        messages: list[dict] | None = None,
    ) -> LLMResponse:
        if messages:
            api_messages = messages
        else:
            api_messages = [
                {
                    "role": "system",
                    "content": (
                        "CRITICAL RULE: Extract entities and relationships "
                        "ONLY from the text inside <Input Text> tags in the "
                        "---Data to be Processed--- section. The ---Examples--- "
                        "section is for reference ONLY. Do NOT extract any "
                        "entities or relationships from the Examples section."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        payload = {
            "model": self._model,
            "messages": api_messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        logger.info(
            f"Ollama request: model={self._model}, " f"prompt_len={len(prompt)} chars"
        )

        last_error = None

        for attempt in range(3):
            try:
                data = await asyncio.to_thread(self._sync_generate, payload, 3600.0)

                content = data.get("message", {}).get("content") or ""

                if not content.strip():
                    logger.warning(
                        f"Ollama returned empty content (attempt {attempt + 1}/3). "
                        f"Response keys: {list(data.get('message', {}).keys())}"
                    )
                    last_error = ValueError("Ollama returned empty content")
                    if attempt < 2:
                        await asyncio.sleep(3.0 * (attempt + 1))
                    continue

                prompt_tokens = data.get("prompt_eval_count", 0)
                eval_tokens = data.get("eval_count", 0)
                return LLMResponse(
                    content=content,
                    model=self._model,
                    usage={
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": eval_tokens,
                        "total_tokens": prompt_tokens + eval_tokens,
                    },
                )
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 0
                if status_code in (400, 401, 403, 404):
                    if status_code in (401, 403):
                        raise requests.exceptions.HTTPError(
                            (
                                "Ollama authorization failed "
                                f"(HTTP {status_code}) for {self._base_url}. "
                                "Проверьте OLLAMA_API_KEY и OLLAMA_BASE_URL."
                            ),
                            response=e.response,
                            request=e.request,
                        ) from e
                    raise
                last_error = e
                if attempt < 2:
                    wait_time = 2.0 * (2**attempt)
                    logger.warning(
                        f"Ollama HTTP {status_code}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2.0 * (2**attempt)
                    logger.warning(
                        f"Ollama error: {e}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait_time)

        raise last_error
