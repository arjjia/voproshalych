"""Сервис праздничной рассылки."""

from __future__ import annotations

import hashlib
import json
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import and_, extract, or_, text

from config import settings
from db import Holiday, TelemetryLog, User, get_session
from services.qa_service_client import QAServiceClient


logger = logging.getLogger(__name__)

VK_API_VERSION = "5.199"
MAX_SEND_ENDPOINT = "/internal/send"
NEWSLETTER_SUMMARY_SERVICE = "holiday_newsletter"
NEWSLETTER_DELIVERY_SERVICE = "holiday_newsletter_delivery"


@dataclass(slots=True)
class HolidayNewsletterResult:
    """Результат отправки праздничной рассылки."""

    holiday_name: str | None
    generated_message: str | None
    sent_count: int
    skipped_count: int
    failed_count: int
    details: list[str]


class HolidayNewsletterService:
    """Подготавливает и отправляет праздничную рассылку подписчикам."""

    def __init__(self, qa_service_client: QAServiceClient) -> None:
        """Инициализирует зависимости сервиса.

        Args:
            qa_service_client: Клиент обращения к QA-сервису.
        """

        self._qa_service_client = qa_service_client

    def send_today_newsletter(self, today: date | None = None) -> HolidayNewsletterResult:
        """Отправляет праздничную рассылку за текущую дату.

        Args:
            today: Дата поиска праздника.

        Returns:
            HolidayNewsletterResult: Сводка по отправке.
        """

        today = today or self._local_today()
        holiday = self.get_today_holiday(today=today)
        if holiday is None:
            return HolidayNewsletterResult(
                holiday_name=None,
                generated_message=None,
                sent_count=0,
                skipped_count=0,
                failed_count=0,
                details=["На текущую дату праздник не найден."],
            )

        users = self.get_subscribed_users()
        if not users:
            return HolidayNewsletterResult(
                holiday_name=holiday.name,
                generated_message=None,
                sent_count=0,
                skipped_count=0,
                failed_count=0,
                details=["Нет подписанных пользователей для рассылки."],
            )

        newsletter_key = self._build_newsletter_key(today=today, holiday=holiday)
        lock_session = get_session()
        if not self._acquire_newsletter_lock(lock_session, newsletter_key):
            lock_session.close()
            return HolidayNewsletterResult(
                holiday_name=holiday.name,
                generated_message=None,
                sent_count=0,
                skipped_count=0,
                failed_count=0,
                details=["Праздничная рассылка уже выполняется другим процессом."],
            )

        message_text = self._qa_service_client.generate_holiday_greeting(
            holiday_name=holiday.name,
            holiday_type=holiday.type,
        )

        try:
            sent_recipient_keys = self._get_sent_recipient_keys(lock_session, newsletter_key)
            pending_users = [
                user
                for user in users
                if self._build_recipient_key(newsletter_key, user) not in sent_recipient_keys
            ]

            if not pending_users:
                return HolidayNewsletterResult(
                    holiday_name=holiday.name,
                    generated_message=message_text,
                    sent_count=0,
                    skipped_count=0,
                    failed_count=0,
                    details=["Праздничная рассылка за сегодня уже доставлена всем подписчикам."],
                )

            sent_count = 0
            skipped_count = 0
            failed_count = 0
            details: list[str] = []

            for user in pending_users:
                try:
                    if self._send_to_user(user, message_text):
                        sent_count += 1
                        details.append(
                            f"Отправлено пользователю {user.platform}:{user.platform_user_id}"
                        )
                        self._mark_delivery_sent(lock_session, newsletter_key, user)
                    else:
                        skipped_count += 1
                        details.append(
                            f"Пропущен пользователь {user.platform}:{user.platform_user_id}"
                        )
                except Exception as exc:
                    failed_count += 1
                    details.append(
                        f"Ошибка отправки {user.platform}:{user.platform_user_id}: {exc}"
                    )
                    logger.exception(
                        "Не удалось отправить праздничную рассылку пользователю %s:%s",
                        user.platform,
                        user.platform_user_id,
                    )

            result = HolidayNewsletterResult(
                holiday_name=holiday.name,
                generated_message=message_text,
                sent_count=sent_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                details=details,
            )
            self._mark_summary(lock_session, newsletter_key, result)
            return result
        finally:
            self._release_newsletter_lock(lock_session, newsletter_key)
            lock_session.close()

    def get_today_holiday(self, today: date | None = None) -> Holiday | None:
        """Возвращает праздник на указанную дату.

        Args:
            today: Дата проверки.

        Returns:
            Holiday | None: Найденный праздник или `None`.
        """

        today = today or date.today()
        session = get_session()
        try:
            return (
                session.query(Holiday)
                .filter(
                    or_(
                        and_(
                            Holiday.month == today.month,
                            Holiday.day_of_month == today.day,
                        ),
                        and_(
                            extract("month", Holiday.date) == today.month,
                            extract("day", Holiday.date) == today.day,
                        ),
                    )
                )
                .order_by(Holiday.id.asc())
                .first()
            )
        finally:
            session.close()

    def get_subscribed_users(self) -> list[User]:
        """Возвращает всех пользователей с активной подпиской.

        Returns:
            list[User]: Подписанные пользователи.
        """

        session = get_session()
        try:
            return session.query(User).filter(User.is_subscribed.is_(True)).all()
        finally:
            session.close()

    def _send_to_user(self, user: User, message_text: str) -> bool:
        """Отправляет поздравление пользователю нужной платформы.

        Args:
            user: Пользователь из БД.
            message_text: Текст поздравления.

        Returns:
            bool: `True`, если сообщение отправлено.
        """

        if user.platform == "telegram":
            return self._send_telegram_message(user.platform_user_id, message_text)
        if user.platform == "vk":
            return self._send_vk_message(user.platform_user_id, message_text)
        if user.platform == "max":
            return self._send_max_message(user.platform_user_id, message_text)
        return False

    def _send_telegram_message(self, chat_id: str, text: str) -> bool:
        """Отправляет сообщение в Telegram."""

        if not settings.telegram_bot_token:
            return False

        response = httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("ok"))

    def _send_vk_message(self, peer_id: str, text: str) -> bool:
        """Отправляет сообщение в VK."""

        if not settings.vk_bot_token:
            return False

        response = httpx.post(
            "https://api.vk.com/method/messages.send",
            data={
                "access_token": settings.vk_bot_token,
                "v": VK_API_VERSION,
                "peer_id": peer_id,
                "random_id": random.randint(1, 2_147_483_647),
                "message": text,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        return "response" in payload

    def _send_max_message(self, user_id: str, text: str) -> bool:
        """Отправляет сообщение в MAX через внутренний endpoint адаптера."""

        response = httpx.post(
            f"{settings.max_bot_internal_url.rstrip('/')}{MAX_SEND_ENDPOINT}",
            json={
                "user_id": user_id,
                "text": text,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("ok"))

    def has_sent_today(self, holiday_name: str, today: date | None = None) -> bool:
        """Проверяет наличие успешной сводки рассылки за локальную дату.

        Метод оставлен для ручной диагностики и не используется как основной
        механизм дедупликации. От повторной отправки защищают advisory lock и
        per-user delivery логи.
        """

        today = today or self._local_today()
        start_of_day = self._start_of_local_day(today)
        end_of_day = self._start_of_next_local_day(today)

        session = get_session()
        try:
            log_entry = (
                session.query(TelemetryLog)
                .filter(
                    TelemetryLog.service == NEWSLETTER_SUMMARY_SERVICE,
                    TelemetryLog.level == "INFO",
                    TelemetryLog.timestamp >= start_of_day,
                    TelemetryLog.timestamp < end_of_day,
                    TelemetryLog.payload.ilike(f'%"{holiday_name}"%'),
                )
                .order_by(TelemetryLog.id.desc())
                .first()
            )
            return log_entry is not None
        finally:
            session.close()

    def _build_newsletter_key(self, today: date, holiday: Holiday) -> str:
        """Строит стабильный ключ рассылки на день и праздник."""

        holiday_identity = holiday.id if holiday.id is not None else holiday.name
        return f"holiday-newsletter:{today.isoformat()}:{holiday_identity}"

    def _build_recipient_key(self, newsletter_key: str, user: User) -> str:
        """Строит ключ доставки для конкретного пользователя."""

        return f"{newsletter_key}:{user.platform}:{user.platform_user_id}"

    def _get_sent_recipient_keys(self, session, newsletter_key: str) -> set[str]:
        """Возвращает ключи пользователей, которым уже отправлена рассылка."""

        rows = (
            session.query(TelemetryLog.request_id)
            .filter(
                TelemetryLog.service == NEWSLETTER_DELIVERY_SERVICE,
                TelemetryLog.level == "INFO",
                TelemetryLog.request_id.like(f"{newsletter_key}:%"),
            )
            .all()
        )
        return {row[0] for row in rows if row[0]}

    def _mark_delivery_sent(self, session, newsletter_key: str, user: User) -> None:
        """Фиксирует успешную доставку пользователю."""

        request_id = self._build_recipient_key(newsletter_key, user)
        try:
            session.add(
                TelemetryLog(
                    level="INFO",
                    request_id=request_id,
                    service=NEWSLETTER_DELIVERY_SERVICE,
                    payload=json.dumps(
                        {
                            "platform": user.platform,
                            "platform_user_id": user.platform_user_id,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Не удалось записать лог доставки праздничной рассылки")

    def _mark_summary(
        self,
        session,
        newsletter_key: str,
        result: HolidayNewsletterResult,
    ) -> None:
        """Фиксирует сводку очередного запуска рассылки."""

        try:
            session.add(
                TelemetryLog(
                    level="INFO",
                    request_id=newsletter_key,
                    service=NEWSLETTER_SUMMARY_SERVICE,
                    payload=json.dumps(
                        {
                            "holiday_name": result.holiday_name,
                            "sent_count": result.sent_count,
                            "skipped_count": result.skipped_count,
                            "failed_count": result.failed_count,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Не удалось записать сводку праздничной рассылки")

    def _acquire_newsletter_lock(self, session, newsletter_key: str) -> bool:
        """Пытается взять advisory lock на текущую рассылку."""

        lock_id = self._build_lock_id(newsletter_key)
        result = session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        return bool(result.scalar())

    def _release_newsletter_lock(self, session, newsletter_key: str) -> None:
        """Освобождает advisory lock рассылки."""

        lock_id = self._build_lock_id(newsletter_key)
        try:
            session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id},
            )
        except Exception:
            logger.exception("Не удалось освободить advisory lock рассылки")

    def _build_lock_id(self, newsletter_key: str) -> int:
        """Преобразует строковый ключ рассылки в bigint для advisory lock."""

        digest = hashlib.sha256(newsletter_key.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF

    def _local_now(self) -> datetime:
        """Возвращает локальное время процесса с учетом timezone контейнера."""

        return datetime.now().astimezone()

    def _local_today(self) -> date:
        """Возвращает локальную дату процесса."""

        return self._local_now().date()

    def _start_of_local_day(self, current_date: date) -> datetime:
        """Возвращает начало локального дня."""

        now = self._local_now()
        return datetime.combine(current_date, datetime.min.time(), tzinfo=now.tzinfo)

    def _start_of_next_local_day(self, current_date: date) -> datetime:
        """Возвращает начало следующего локального дня."""
        return self._start_of_local_day(current_date) + timedelta(days=1)
