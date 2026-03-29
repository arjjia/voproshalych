"""FastAPI-приложение, которое отдает общую бизнес-логику бота."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI

logger = logging.getLogger(__name__)

from config import settings
from models.callback import CallbackEvent
from models.message import IncomingMessage
from models.response import BotResponse
from services.bot_service import BotService


bot_service = BotService()


def _get_next_newsletter_delay_seconds(now: datetime | None = None) -> float:
    """Вычисляет задержку до следующего запуска рассылки."""

    now = now or datetime.now().astimezone()
    target = now.replace(
        hour=settings.holiday_newsletter_run_hour,
        minute=settings.holiday_newsletter_run_minute,
        second=0,
        microsecond=0,
    )
    if target <= now:
        target = target + timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)


def _is_newsletter_due(now: datetime | None = None) -> bool:
    """Проверяет, что локальное время уже достигло окна рассылки."""

    now = now or datetime.now().astimezone()
    target = now.replace(
        hour=settings.holiday_newsletter_run_hour,
        minute=settings.holiday_newsletter_run_minute,
        second=0,
        microsecond=0,
    )
    return now >= target


async def _run_holiday_newsletter(reason: str) -> None:
    """Запускает рассылку и пишет единый лог результата."""

    try:
        result = await asyncio.to_thread(bot_service.send_today_holiday_newsletter)
        logger.info(
            "Праздничная рассылка выполнена (%s): holiday=%s sent=%s skipped=%s failed=%s",
            reason,
            result.get("holiday_name"),
            result.get("sent_count"),
            result.get("skipped_count"),
            result.get("failed_count"),
        )
    except Exception:
        logger.exception("Ошибка запуска праздничной рассылки (%s)", reason)


async def _holiday_newsletter_loop() -> None:
    """Фоновый цикл ежедневного запуска праздничной рассылки."""

    while True:
        delay_seconds = _get_next_newsletter_delay_seconds()
        logger.info(
            "Следующий запуск праздничной рассылки через %.0f секунд",
            delay_seconds,
        )
        await asyncio.sleep(delay_seconds)
        await _run_holiday_newsletter("scheduled")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Управляет жизненным циклом приложения."""

    task: asyncio.Task | None = None
    if settings.holiday_newsletter_enabled:
        if _is_newsletter_due():
            await _run_holiday_newsletter("startup-catchup")
        task = asyncio.create_task(_holiday_newsletter_loop())

    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Возвращает статус доступности сервиса."""

    return {"status": "ok"}


@app.post("/messages", response_model=BotResponse)
def process_message(message: IncomingMessage) -> BotResponse:
    """Обрабатывает нормализованное сообщение через общую бизнес-логику.

    Args:
        message: Нормализованное сообщение, полученное от адаптера платформы.

    Returns:
        BotResponse: Действия, которые должен выполнить вызывающий адаптер.
    """

    logger.info("Received message payload: %s", message.model_dump())
    return bot_service.handle_message(message)


@app.post("/callbacks", response_model=BotResponse)
def process_callback(event: CallbackEvent) -> BotResponse:
    """Обрабатывает callback-событие через общую бизнес-логику.

    Args:
        event: Callback-событие от адаптера платформы.

    Returns:
        BotResponse: Действия, которые должен выполнить вызывающий адаптер.
    """

    return bot_service.handle_callback(event)


@app.post("/newsletters/holidays/send-today")
def send_today_holiday_newsletter() -> dict[str, object]:
    """Запускает праздничную рассылку за текущую дату.

    Returns:
        dict[str, object]: Сводка по отправке.
    """

    return bot_service.send_today_holiday_newsletter()
