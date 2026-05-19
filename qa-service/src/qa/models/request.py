"""Модели запросов и ответов."""

from pydantic import BaseModel, Field


class SourceLink(BaseModel):
    """Источник для отображения inline-кнопкой.

    Attributes:
        url: URL источника.
        label: Текст кнопки (например, «Подробнее 1»).
    """

    url: str
    label: str = "Подробнее"


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
        answer: Ответ от LLM (чистый текст без markdown)
        model: Использованная модель
        sources: Источники с URL и label для inline-кнопок
        expanded_query: Расширенный запрос (опционально)
        context_expanded_query: Расширенный запрос с учётом контекста (опционально)
        keywords: Ключевые слова (опционально)
        question_type: Тип вопроса (1=БЗ, 2=система, 3=общий)
        relevance_type: Релевантность ответа для БЗ: a=отвечено, b=нет информации
        relevant_sources: Номера релевантных источников
    """

    answer: str
    model: str
    sources: list[SourceLink] = Field(default_factory=list)
    expanded_query: str | None = Field(default=None, max_length=1500)
    context_expanded_query: str | None = Field(default=None, max_length=1500)
    keywords: dict | None = Field(default=None)
    question_type: int = Field(default=1)
    relevance_type: str | None = Field(default=None, max_length=1)
    relevant_sources: list[int] = Field(default_factory=list)


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
