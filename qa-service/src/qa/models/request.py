"""Модели запросов и ответов."""

from pydantic import BaseModel, Field


class QARequest(BaseModel):
    """Запрос к QA сервису.

    Attributes:
        question: Вопрос пользователя
        context: Дополнительный контекст (опционально)
    """

    question: str = Field(..., min_length=1, max_length=10000)
    context: str | None = None


class QAResponse(BaseModel):
    """Ответ от QA сервиса.

    Attributes:
        answer: Ответ от LLM
        model: Использованная модель
        sources: Источники (если есть)
    """

    answer: str
    model: str
    sources: list[str] = Field(default_factory=list)


class HolidayGreetingRequest(BaseModel):
    """Запрос на генерацию праздничного поздравления.

    Attributes:
        holiday_name: Название праздника.
        holiday_type: Тип праздника, если он известен.
        recipient_name: Имя получателя, если есть.
        style: Желаемый стиль поздравления.
        max_length: Максимальная длина текста.
    """

    holiday_name: str = Field(..., min_length=1, max_length=255)
    holiday_type: str | None = Field(default=None, max_length=50)
    recipient_name: str | None = Field(default=None, max_length=255)
    style: str = Field(default="дружелюбный", max_length=50)
    max_length: int = Field(default=300, ge=50, le=1000)


class HolidayGreetingResponse(BaseModel):
    """Ответ с текстом праздничного поздравления."""

    message: str
    model: str


class HealthResponse(BaseModel):
    """Ответ health check."""

    status: str
    version: str
