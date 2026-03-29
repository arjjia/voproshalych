"""API роут для генерации праздничных поздравлений."""

import logging

from fastapi import APIRouter, HTTPException

from ...config.prompts import HOLIDAY_GREETING_PROMPT
from ...llm import get_llm_pool
from ...models.request import HolidayGreetingRequest, HolidayGreetingResponse


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa/holiday", tags=["holiday"])


@router.post("", response_model=HolidayGreetingResponse)
async def generate_holiday_greeting(
    request: HolidayGreetingRequest,
) -> HolidayGreetingResponse:
    """Генерирует короткое поздравление по названию праздника.

    Args:
        request: Параметры генерации поздравления.

    Returns:
        HolidayGreetingResponse: Готовый текст поздравления и модель.
    """

    llm_pool = get_llm_pool()
    provider_name = llm_pool.select_model()
    if not provider_name:
        raise HTTPException(status_code=503, detail="No available LLM providers")

    prompt_parts = [
        HOLIDAY_GREETING_PROMPT,
        f"Праздник: {request.holiday_name}",
        f"Стиль: {request.style}",
        f"Максимальная длина: {request.max_length} символов",
    ]

    if request.holiday_type:
        prompt_parts.append(f"Тип праздника: {request.holiday_type}")
    if request.recipient_name:
        prompt_parts.append(f"Имя получателя: {request.recipient_name}")

    prompt_parts.append("Напиши одно итоговое поздравление.")
    prompt = "\n".join(prompt_parts)

    try:
        response = await llm_pool.call(prompt=prompt)
        return HolidayGreetingResponse(
            message=response.content.strip(),
            model=response.model,
        )
    except ValueError as exc:
        logger.error(f"Holiday greeting generation failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Не удалось сгенерировать поздравление: нет доступных провайдеров.",
        ) from exc
    except Exception as exc:
        logger.error(f"Unexpected holiday greeting error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Не удалось сгенерировать поздравление.",
        ) from exc
