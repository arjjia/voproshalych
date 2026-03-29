"""Telegram-адаптер на базе aiogram.

Модуль принимает обновления Telegram, нормализует их к общему контракту core,
отправляет в FastAPI-сервис и выполняет возвращенные действия.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


logging.basicConfig(level=logging.INFO)


@dataclass(slots=True)
class Settings:
    """Настройки запуска Telegram-адаптера."""

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot_core_url: str = os.getenv("BOT_CORE_URL", "http://127.0.0.1:8000")
    request_timeout_seconds: float = float(os.getenv("BOT_CORE_TIMEOUT_SECONDS", "300"))


class CoreClient:
    """Асинхронный HTTP-клиент для общего bot core."""

    def __init__(self, settings: Settings) -> None:
        """Инициализирует HTTP-клиент.

        Args:
            settings: Настройки запуска Telegram-адаптера.
        """

        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.bot_core_url.rstrip("/"),
            timeout=settings.request_timeout_seconds,
        )

    async def close(self) -> None:
        """Закрывает внутренний HTTP-клиент."""

        await self._client.aclose()

    async def process_message(self, message: Message) -> dict[str, Any]:
        """Отправляет нормализованное сообщение Telegram в core-сервис.

        Args:
            message: Сообщение Telegram, полученное через aiogram.

        Returns:
            dict[str, Any]: JSON-ответ от core-сервиса.
        """

        payload = self._build_payload(message)
        response = await self._client.post("/messages", json=payload)
        response.raise_for_status()
        return response.json()

    async def process_callback(self, callback: CallbackQuery) -> dict[str, Any]:
        """Отправляет callback Telegram в core-сервис.

        Args:
            callback: Callback-событие Telegram.

        Returns:
            dict[str, Any]: JSON-ответ от core-сервиса.
        """

        payload = {
            "platform": "telegram",
            "user_id": str(callback.from_user.id),
            "chat_id": str(callback.message.chat.id) if callback.message else "",
            "callback_data": callback.data or "",
            "message_id": str(callback.message.message_id)
            if callback.message
            else None,
            "metadata": {},
        }
        response = await self._client.post("/callbacks", json=payload)
        response.raise_for_status()
        return response.json()

    def _build_payload(self, message: Message) -> dict[str, Any]:
        """Преобразует сообщение Telegram в общий контракт core.

        Args:
            message: Сообщение Telegram, полученное через aiogram.

        Returns:
            dict[str, Any]: JSON-полезная нагрузка по входной схеме core.
        """

        sent_at = (
            message.date.astimezone(UTC).isoformat()
            if message.date
            else datetime.now(UTC).isoformat()
        )

        return {
            "platform": "telegram",
            "message_type": detect_message_type(message),
            "user_id": str(message.from_user.id),
            "chat_id": str(message.chat.id),
            "text": message.text or "",
            "message_id": str(message.message_id),
            "timestamp": sent_at,
            "metadata": {
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
                "chat_type": message.chat.type,
            },
        }


def build_dispatcher(core_client: CoreClient) -> Dispatcher:
    """Создает dispatcher aiogram и подключает обработчики сообщений.

    Args:
        core_client: HTTP-клиент для общего core-сервиса.

    Returns:
        Dispatcher: Настроенный dispatcher aiogram.
    """

    dispatcher = Dispatcher()

    @dispatcher.message()
    async def handle_message(message: Message) -> None:
        """Проксирует сообщения в core-сервис и выполняет действия.

        Args:
            message: Сообщение Telegram, полученное через aiogram.
        """

        if not message.from_user:
            return

        pending_message: Message | None = None
        if should_show_pending_message(message):
            pending_message = await message.answer("Ищу ответ на ваш вопрос...")

        try:
            bot_response = await core_client.process_message(message)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logging.error(
                f"HTTP error from core: {status_code} - {e.response.text[:200]}"
            )
            await delete_message_safely(pending_message)

            if status_code == 503:
                await message.answer(
                    "Сервис временно недоступен. "
                    "Пожалуйста, попробуйте через несколько минут."
                )
            elif status_code >= 500:
                await message.answer(
                    "Произошла внутренняя ошибка сервиса. "
                    "Мы уже работаем над её устранением."
                )
            else:
                await message.answer(
                    "Не удалось обработать запрос. Попробуйте переформулировать вопрос."
                )
            return
        except httpx.TimeoutException:
            logging.error("Timeout connecting to core service")
            await delete_message_safely(pending_message)
            await message.answer(
                "Поиск ответа занимает слишком долго. "
                "Попробуйте переформулировать вопрос."
            )
            return
        except httpx.ConnectError:
            logging.error("Cannot connect to core service")
            await delete_message_safely(pending_message)
            await message.answer(
                "Не удалось подключиться к сервису. "
                "Проверьте подключение и попробуйте позже."
            )
            return
        except httpx.HTTPError:
            logging.exception("Failed to process Telegram message via core")
            await delete_message_safely(pending_message)
            await message.answer("Что-то пошло не так. Пожалуйста, попробуйте ещё раз.")
            return

        await delete_message_safely(pending_message)

        for action in bot_response.get("actions", []):
            if action.get("type") == "send_text" and action.get("text"):
                await message.answer(
                    action["text"],
                    reply_markup=build_inline_keyboard(action.get("buttons", [])),
                )

    @dispatcher.callback_query()
    async def handle_callback(callback: CallbackQuery) -> None:
        """Проксирует callback в core и выполняет действия.

        Args:
            callback: Callback-событие Telegram.
        """
        try:
            bot_response = await core_client.process_callback(callback)
        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP error from core: {e.response.status_code}")
            await callback.answer("Сервис временно недоступен.")
            return
        except httpx.TimeoutException:
            logging.error("Timeout connecting to core service")
            await callback.answer("Сервис временно недоступен.")
            return
        except httpx.HTTPError:
            logging.exception("Failed to process Telegram callback via core")
            await callback.answer("Сервис временно недоступен.")
            return

        for action in bot_response.get("actions", []):
            if action.get("buttons") and callback.message:
                await callback.message.edit_reply_markup(
                    reply_markup=build_inline_keyboard(action["buttons"])
                )

            if action.get("text"):
                if callback.message:
                    await callback.message.answer(action["text"])
                else:
                    await callback.answer(action["text"])
                    return

        await callback.answer()

    return dispatcher


def build_inline_keyboard(
    button_rows: list[list[dict[str, str]]],
) -> InlineKeyboardMarkup | None:
    """Преобразует кнопки из ответа core в Telegram inline keyboard.

    Args:
        button_rows: Строки кнопок из ответа core.

    Returns:
        InlineKeyboardMarkup | None: Готовая клавиатура или `None`.
    """

    if not button_rows:
        return None

    inline_keyboard = []
    for row in button_rows:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=button["text"],
                    callback_data=button["callback_data"],
                )
                for button in row
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def detect_message_type(message: Message) -> str:
    """Определяет платформенно-независимый тип сообщения Telegram.

    Args:
        message: Сообщение Telegram.

    Returns:
        str: Тип сообщения для контракта core.
    """

    if message.voice:
        return "voice"
    if message.sticker:
        return "sticker"
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.audio:
        return "audio"
    if message.document:
        return "document"
    if message.text:
        return "text"
    return "unknown"


def should_show_pending_message(message: Message) -> bool:
    """Определяет, нужно ли показывать временное сообщение ожидания.

    Args:
        message: Сообщение Telegram.

    Returns:
        bool: `True`, если нужно показать сообщение ожидания.
    """

    if detect_message_type(message) != "text":
        return False

    normalized_text = (message.text or "").strip().lower()
    return normalized_text not in {"/start", "/ping"}


async def delete_message_safely(message: Message | None) -> None:
    """Пытается удалить сообщение без проброса исключения наружу.

    Args:
        message: Сообщение, которое нужно удалить.
    """

    if message is None:
        return

    try:
        await message.delete()
    except Exception:
        logging.exception("Failed to delete pending Telegram message")


async def main() -> None:
    """Запускает polling Telegram и пересылает сообщения в core-сервис."""

    settings = Settings()

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_bot_token)
    core_client = CoreClient(settings)
    dispatcher = build_dispatcher(core_client)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await core_client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
