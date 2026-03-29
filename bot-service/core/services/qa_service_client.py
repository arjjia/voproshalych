"""Клиент для обращения к QA-сервису с retry логикой."""

import logging
import time
import httpx


logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 8.0


class QAServiceError(Exception):
    """Базовый класс для ошибок QA-сервиса."""

    pass


class QAServiceTimeout(QAServiceError):
    """Превышен таймаут."""

    pass


class QAServiceUnavailable(QAServiceError):
    """QA-сервис недоступен."""

    pass


class QAServiceLLMError(QAServiceError):
    """Ошибка генерации ответа LLM."""

    pass


class QAServiceClient:
    """Синхронный HTTP-клиент для QA-сервиса с retry."""

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
        self._max_retries = MAX_RETRIES

    def ask(self, question: str, context: str | None = None) -> str:
        """Отправляет вопрос в QA-сервис с retry логикой.

        Args:
            question: Вопрос пользователя.
            context: Дополнительный контекст.

        Returns:
            str: Ответ QA-сервиса.

        Raises:
            QAServiceError: При ошибке после всех попыток.
        """
        last_error: Exception | None = None
        backoff = INITIAL_BACKOFF

        for attempt in range(self._max_retries):
            try:
                response = self._client.post(
                    "/qa",
                    json={
                        "question": question,
                        "context": context,
                    },
                )

                if response.status_code == 503:
                    logger.warning(
                        f"QA service unavailable (attempt {attempt + 1}/{self._max_retries})"
                    )
                    last_error = QAServiceUnavailable(
                        "QA service is unavailable, retrying..."
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue

                if response.status_code >= 500:
                    logger.warning(
                        f"QA service error {response.status_code} (attempt {attempt + 1}/{self._max_retries})"
                    )
                    last_error = QAServiceError(
                        f"QA service error: {response.status_code}"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue

                response.raise_for_status()
                payload = response.json()
                return payload["answer"]

            except httpx.TimeoutException as e:
                logger.warning(
                    f"QA service timeout (attempt {attempt + 1}/{self._max_retries})"
                )
                last_error = QAServiceTimeout("QA service timeout")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code == 429:
                    logger.warning(
                        f"Rate limited by QA service (attempt {attempt + 1}/{self._max_retries})"
                    )
                    time.sleep(backoff * 2)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue

                logger.error(f"QA service HTTP error: {status_code}")
                if status_code == 400:
                    raise QAServiceError(f"Invalid request: {e.response.text[:100]}")
                raise

            except httpx.ConnectError as e:
                logger.warning(
                    f"Cannot connect to QA service (attempt {attempt + 1}/{self._max_retries})"
                )
                last_error = QAServiceUnavailable("Cannot connect to QA service")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

            except Exception as e:
                logger.error(f"Unexpected error: {type(e).__name__}: {e}")
                raise QAServiceError(f"Unexpected error: {str(e)}")

        if last_error:
            raise last_error

        raise QAServiceError("Failed to get answer after all retries")

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

        try:
            response = self._client.post(
                "/qa/holiday",
                json={
                    "holiday_name": holiday_name,
                    "holiday_type": holiday_type,
                    "recipient_name": recipient_name,
                    "style": style,
                    "max_length": max_length,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return payload["message"]
        except Exception as exc:
            raise QAServiceError(
                f"Failed to generate holiday greeting: {exc}"
            ) from exc
