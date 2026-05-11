"""Клиент для обращения к QA-сервису."""

import logging
import uuid

import httpx


logger = logging.getLogger(__name__)


class QAServiceError(Exception):
    """Базовый класс для ошибок QA-сервиса."""

    pass


class QAServiceTimeout(QAServiceError):
    """Превышен таймаут."""

    pass


class QAServiceUnavailable(QAServiceError):
    """QA-сервис недоступен."""

    pass


class QAServiceRateLimited(QAServiceError):
    """QA-сервис временно ограничивает запросы."""

    pass


class QAServiceLLMError(QAServiceError):
    """Ошибка генерации ответа LLM."""

    pass


class QAServiceClient:
    """Синхронный HTTP-клиент для QA-сервиса.

    Для неидемпотентных POST-запросов не использует автоматические ретраи:
    один вызов клиента соответствует одной попытке обращения к QA-сервису.
    """

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        """Инициализирует клиента QA-сервиса.

        Args:
            base_url: Базовый URL QA-сервиса.
            timeout_seconds: Таймаут запросов в секундах.
        """

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    def ask(self, question: str, context: str | None = None) -> dict:
        """Отправляет вопрос в QA-сервис одной попыткой.

        Args:
            question: Вопрос пользователя.
            context: Дополнительный контекст.

        Returns:
            dict: Ответ QA-сервиса с ключами:
                - answer: str — текст ответа
                - expanded_query: str | None — расширенный запрос
                - keywords: dict | None — извлечённые ключевые слова
                - model: str — модель
                - sources: list[str] — URL источников
                - question_type: int — тип вопроса (1/2/3)

        Raises:
            QAServiceError: При ошибке запроса.
        """
        request_id = uuid.uuid4().hex[:8]
        headers = {"X-Request-ID": request_id}
        payload = self._post_json(
            "/qa",
            {
                "question": question,
                "context": context,
            },
            headers=headers,
        )
        return {
            "answer": payload.get("answer", ""),
            "expanded_query": payload.get("expanded_query"),
            "context_expanded_query": payload.get("context_expanded_query"),
            "keywords": payload.get("keywords"),
            "model": payload.get("model", ""),
            "sources": payload.get("sources", []),
            "question_type": payload.get("question_type", 1),
        }

    def generate_holiday_greeting(
        self,
        holiday_name: str,
        holiday_type: str | None = None,
        recipient_name: str | None = None,
        style: str = "дружелюбный",
        max_length: int = 300,
    ) -> str:
        """Запрашивает у QA-сервиса короткое поздравление с праздником.

        Args:
            holiday_name: Название праздника.
            holiday_type: Тип праздника.
            recipient_name: Имя получателя.
            style: Желаемый стиль поздравления.
            max_length: Ограничение длины текста.

        Returns:
            str: Готовый текст поздравления.
        """
        payload = self._post_json(
            "/qa/holiday",
            {
                "holiday_name": holiday_name,
                "holiday_type": holiday_type,
                "recipient_name": recipient_name,
                "style": style,
                "max_length": max_length,
            },
        )
        return payload["message"]

    def _post_json(
        self,
        path: str,
        payload: dict[str, object],
        headers: dict | None = None,
    ) -> dict[str, object]:
        """Выполнить одиночный POST-запрос и преобразовать ошибки в доменные."""
        try:
            response = self._client.post(path, json=payload, headers=headers or {})
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            logger.warning("QA service timeout on %s", path)
            raise QAServiceTimeout("QA service timeout") from exc
        except httpx.ConnectError as exc:
            logger.warning("Cannot connect to QA service on %s", path)
            raise QAServiceUnavailable("Cannot connect to QA service") from exc
        except httpx.HTTPStatusError as exc:
            raise self._map_http_error(exc) from exc
        except Exception as exc:
            logger.error("Unexpected error on %s: %s: %s", path, type(exc).__name__, exc)
            raise QAServiceError(f"Unexpected error: {str(exc)}") from exc

    def _map_http_error(self, exc: httpx.HTTPStatusError) -> QAServiceError:
        """Преобразовать HTTP-ошибку QA-сервиса в доменное исключение."""
        status_code = exc.response.status_code
        response_snippet = exc.response.text[:200]

        if status_code == 429:
            logger.warning("QA service rate limited on %s", exc.request.url.path)
            return QAServiceRateLimited("QA service rate limited")

        if status_code in (503, 504):
            logger.warning("QA service unavailable on %s", exc.request.url.path)
            return QAServiceUnavailable("QA service is unavailable")

        if status_code in (400, 422):
            logger.error("QA service invalid request on %s", exc.request.url.path)
            return QAServiceError(f"Invalid request: {response_snippet}")

        if status_code >= 500:
            logger.error(
                "QA service HTTP error %s on %s",
                status_code,
                exc.request.url.path,
            )
            return QAServiceError(f"QA service error: {status_code}")

        logger.error(
            "QA service unexpected HTTP error %s on %s",
            status_code,
            exc.request.url.path,
        )
        return QAServiceError(f"QA service HTTP error: {status_code}")
