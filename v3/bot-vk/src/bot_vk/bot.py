from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import re
from vkbottle import Callback, Keyboard, Text, OpenLink
from vkbottle.bot import Bot, Message


logging.basicConfig(level=logging.INFO)

_MSG_SERVICE_UNAVAILABLE = "Сервис временно недоступен. Попробуйте позже."
_MSG_PENDING = "Сейчас я попробую ответить на этот вопрос, это может занять какое-то время..."


@dataclass(slots=True)
class Settings:
    vk_bot_token: str = os.getenv("VK_BOT_TOKEN", "")
    bot_core_url: str = os.getenv("BOT_CORE_URL", "http://agent-service:8001")
    request_timeout_seconds: float = float(
        os.getenv("BOT_CORE_TIMEOUT_SECONDS", "10")
    )


class AgentClient:
    def __init__(self, settings: Settings) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.bot_core_url.rstrip("/"),
            timeout=settings.request_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def process_message(self, message: Message) -> dict[str, Any]:
        payload = {"query": message.text or ""}
        response = await self._client.post("/chat", json=payload)
        response.raise_for_status()
        return response.json()


def build_bot(settings: Settings, agent_client: AgentClient) -> Bot:
    bot = Bot(settings.vk_bot_token)

    @bot.on.message()
    async def handle_start_or_message(message: Message) -> None:
        text = (message.text or "").strip().lower()
        is_start = text in {"/start", "start", "начать"}
        is_quick_button = text in {"помощь", "новый диалог", "рассылка", "📋 помощь", "🔄 новый диалог", "🔔 рассылка"}

        pending_message_id: int | None = None
        if should_show_pending_message(message) and not is_start and not is_quick_button:
            pending_message_id = await send_pending_message(bot, message)

        try:
            bot_response = await agent_client.process_message(message)
        except httpx.HTTPError:
            logging.exception("Не удалось обработать сообщение VK через agent")
            await delete_pending_message(bot, pending_message_id)
            await message.answer(_MSG_SERVICE_UNAVAILABLE)
            return

        await delete_pending_message(bot, pending_message_id)

        answer = bot_response.get("answer", "")
        if answer:
            answer = _strip_html_to_plain(answer)
            try:
                await message.answer(answer)
            except Exception:
                logging.exception("Failed to send VK message")

    return bot


def _strip_html_to_plain(text: str) -> str:
    text = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r"\2\n— \1", text)
    return text


def detect_message_type(message: Message) -> str:
    if message.attachments:
        attachment_type = getattr(message.attachments[0], "type", None)
        if attachment_type in {
            "sticker",
            "photo",
            "video",
            "audio",
            "doc",
            "audio_message",
        }:
            if attachment_type == "audio_message":
                return "voice"
            if attachment_type == "doc":
                return "document"
            return attachment_type

    if message.text:
        return "text"
    return "unknown"


def should_show_pending_message(message: Message) -> bool:
    if detect_message_type(message) != "text":
        return False

    normalized_text = (message.text or "").strip().lower()
    return normalized_text not in {"/start", "start", "начать"}


async def send_pending_message(bot: Bot, message: Message) -> int | None:
    try:
        return await bot.api.messages.send(
            peer_id=message.peer_id,
            random_id=random.randint(1, 2_147_483_647),
            message=_MSG_PENDING,
        )
    except Exception:
        logging.exception("Не удалось отправить временное сообщение VK")
        return None


async def delete_pending_message(bot: Bot, message_id: int | None) -> None:
    if message_id is None:
        return

    try:
        await bot.api.messages.delete(
            message_ids=[message_id],
            delete_for_all=1,
        )
    except Exception:
        logging.exception("Не удалось удалить временное сообщение VK")


def main() -> None:
    settings = Settings()
    if not settings.vk_bot_token:
        raise RuntimeError("VK_BOT_TOKEN is not set")

    agent_client = AgentClient(settings)
    bot = build_bot(settings, agent_client)

    try:
        bot.run_forever()
    finally:
        asyncio.run(agent_client.close())


if __name__ == "__main__":
    main()
