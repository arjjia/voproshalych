"""HTTP-клиент для взаимодействия с kb-service v3 через JSON-RPC."""

import json
import logging

import httpx

logger = logging.getLogger(__name__)


class QAServiceClient:
    """Клиент для вызова kb-service через JSON-RPC."""

    def __init__(self, base_url: str, timeout: int = 300):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def ask(self, query: str) -> dict | None:
        """Отправить запрос в kb-service.

        Args:
            query: Текст вопроса

        Returns:
            Словарь с ответом (context, sources и т.д.) или None при ошибке
        """
        url = f"{self._base_url}/api/v1/tools"
        payload = {
            "jsonrpc": "2.0",
            "method": "kb_search",
            "params": {"query": query, "top_k": 10},
            "id": 1,
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True,
            ) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                result = data.get("result", {})
                if not result or not result.get("results"):
                    return None

                raw_results = result.get("results", [])
                sources = [
                    {
                        "url": r.get("source_url", ""),
                        "title": r.get("title", ""),
                        "score": r.get("score", 0),
                    }
                    for r in raw_results if r.get("source_url")
                ]

                return {
                    "answer": result.get("context", ""),
                    "sources": sources,
                    "question_type": None,
                    "model_used": "kb-service",
                }

        except httpx.TimeoutException:
            logger.error(f"kb-service timeout after {self._timeout}s")
            return {"answer": "Сервис временно недоступен (таймаут). Попробуйте позже.", "sources": []}
        except httpx.HTTPStatusError as e:
            logger.error(f"kb-service HTTP error: {e.response.status_code}")
            return {"answer": "Сервис временно недоступен. Попробуйте позже.", "sources": []}
        except Exception as e:
            logger.error(f"kb-service error: {e}")
            return {"answer": "Произошла внутренняя ошибка.", "sources": []}
