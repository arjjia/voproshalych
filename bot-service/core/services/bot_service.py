"""Точка входа в бизнес-логику для обработки нормализованных сообщений."""

import logging
import re

from config import settings
from models.callback import CallbackEvent
from models.message import IncomingMessage
from models.response import ActionType, BotResponse, InlineButton, KeyboardButton, OutgoingAction
from services.dialog_service import DialogService
from services.feedback_service import FeedbackService, FEEDBACK_LIKE, FEEDBACK_DISLIKE
from services.holiday_newsletter import HolidayNewsletterService
from services.qa_service_client import QAServiceClient
from services.user_service import UserService

logger = logging.getLogger(__name__)


class BotService:
    """Обрабатывает нормализованные сообщения и возвращает платформенно-независимые действия."""

    def __init__(self) -> None:
        """Инициализирует зависимости бизнес-логики."""

        self._qa_service_client = QAServiceClient(
            base_url=settings.qa_service_url,
            timeout_seconds=settings.qa_service_timeout_seconds,
        )
        self._dialog_service = DialogService()
        self._feedback_service = FeedbackService()
        self._holiday_newsletter_service = HolidayNewsletterService(
            qa_service_client=self._qa_service_client
        )
        self._user_service = UserService()

    def handle_message(self, message: IncomingMessage) -> BotResponse:
        """Обрабатывает сообщение и возвращает действия для адаптера платформы.

        Args:
            message: Нормализованное входящее сообщение от адаптера платформы.

        Returns:
            BotResponse: Действия, которые нужно выполнить на исходной платформе.
        """

        user = self._user_service.upsert_user(message)

        if message.message_type == "text":
            return self._handle_text_message(message, user)
        if message.message_type == "voice":
            return self._handle_voice_message(message)
        return self._build_unsupported_message_response(message)

    def handle_callback(self, event: CallbackEvent) -> BotResponse:
        """Обрабатывает callback-событие платформы.

        Args:
            event: Нормализованное callback-событие.

        Returns:
            BotResponse: Ответ для callback-события.
        """

        if event.callback_data == "subscription:toggle" or event.callback_data == "menu:subscription":
            user = self._user_service.toggle_subscription(event)
            if user is None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text="Не удалось изменить статус подписки.",
                        )
                    ]
                )

            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text=(
                            "Вы подписались на поздравления с праздниками!"
                            if user.is_subscribed
                            else "Вы отписались от поздравлений."
                        ),
                        buttons=self._build_start_buttons(user.is_subscribed),
                    )
                ]
            )

        if event.callback_data == "menu:help":
            return self._build_help_response()

        if event.callback_data == "dialog:start_new" or event.callback_data == "menu:new_dialog":
            user = self._user_service.get_user(event.platform.value, event.user_id)
            if user is None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text="Не удалось начать новый диалог.",
                        )
                    ]
                )

            dialog_session = self._dialog_service.start_new_dialog(user.id)
            if dialog_session is None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text="Не удалось начать новый диалог.",
                        )
                    ]
                )

            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text="История сброшена! Задавайте новый вопрос 🔄",
                    )
                ]
            )

        if event.callback_data == "feedback:like":
            result = self._feedback_service.save_feedback(
                event.platform.value, event.user_id, FEEDBACK_LIKE,
            )
            if result == "already_rated":
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text="Вы уже оценили этот ответ.",
                        )
                    ]
                )
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text="Рад помочь! 😻",
                    )
                ]
            )

        if event.callback_data == "feedback:dislike":
            result = self._feedback_service.save_feedback(
                event.platform.value, event.user_id, FEEDBACK_DISLIKE,
            )
            if result == "already_rated":
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text="Вы уже оценили этот ответ.",
                        )
                    ]
                )
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text="Спасибо за обратную связь, постараюсь стать лучше! 🐱",
                    )
                ]
            )

        return BotResponse(actions=[])

    def send_today_holiday_newsletter(self) -> dict[str, object]:
        """Запускает праздничную рассылку за текущую дату.

        Returns:
            dict[str, object]: Сводка по отправке.
        """

        result = self._holiday_newsletter_service.send_today_newsletter()
        return {
            "holiday_name": result.holiday_name,
            "generated_message": result.generated_message,
            "sent_count": result.sent_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "details": result.details,
        }

    def _handle_text_message(self, message: IncomingMessage, user) -> BotResponse:
        """Обрабатывает текстовое сообщение.

        Args:
            message: Нормализованное текстовое сообщение.
            user: Текущий пользователь из БД.

        Returns:
            BotResponse: Ответ для текстового сообщения.
        """

        normalized_text = (message.text or "").strip()
        lowered_text = normalized_text.lower()

        if lowered_text == "/start":
            return self._build_start_response(message, user)
        if lowered_text in ("/help", "📋 помощь"):
            return self._build_help_response()
        if lowered_text in ("🔄 новый диалог",):
            if user is not None:
                self._dialog_service.start_new_dialog(user.id)
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text="История сброшена! Задавайте новый вопрос 🔄",
                    )
                ]
            )
        if lowered_text in ("🔔 рассылка",):
            from models.callback import CallbackEvent as CBEvent
            fake_event = CBEvent(
                platform=message.platform,
                user_id=message.user_id,
                chat_id=message.chat_id,
                callback_data="subscription:toggle",
            )
            toggled_user = self._user_service.toggle_subscription(fake_event)
            if toggled_user is not None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=(
                                "Вы подписались на поздравления с праздниками!"
                                if toggled_user.is_subscribed
                                else "Вы отписались от поздравлений."
                            ),
                        )
                    ]
                )
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text="Не удалось изменить статус подписки.",
                    )
                ]
            )
        if self._is_service_command(lowered_text):
            return self._build_service_command_response()

        reply_text = self._handle_dialog_message(normalized_text, user)

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=reply_text,
                    buttons=self._build_feedback_buttons(),
                )
            ]
        )

    def _handle_dialog_message(self, question: str, user) -> str:
        """Обрабатывает пользовательский вопрос с учетом истории диалога.

        Args:
            question: Текущий вопрос пользователя.
            user: Текущий пользователь из БД.

        Returns:
            str: Ответ QA-сервиса или fallback-текст.
        """

        if user is None:
            qa_result = self._ask_qa_service(question)
            return self._format_qa_answer(qa_result)

        dialog_session = self._dialog_service.get_or_create_active_session(user.id)
        if dialog_session is None:
            qa_result = self._ask_qa_service(question)
            return self._format_qa_answer(qa_result)

        history = self._dialog_service.build_context(
            session_id=dialog_session.id,
            max_chars=settings.dialog_context_max_chars,
        )
        qa_result = self._ask_qa_service(
            question=question,
            context=history or None,
        )
        self._dialog_service.save_question_answer(
            session_id=dialog_session.id,
            question=question,
            answer=qa_result.get("answer", ""),
            expanded_query=qa_result.get("expanded_query"),
            keywords=qa_result.get("keywords"),
            model_used=qa_result.get("model"),
        )
        return self._format_qa_answer(qa_result)

    def _handle_voice_message(self, message: IncomingMessage) -> BotResponse:
        """Обрабатывает голосовое сообщение.

        Args:
            message: Нормализованное голосовое сообщение.

        Returns:
            BotResponse: Заглушка до интеграции STT.
        """

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=(
                        "Я получил голосовое сообщение. "
                        "Скоро здесь будет распознавание речи."
                    ),
                )
            ]
        )

    def _build_unsupported_message_response(
        self,
        message: IncomingMessage,
    ) -> BotResponse:
        """Возвращает ответ для неподдерживаемого типа сообщения.

        Args:
            message: Нормализованное входящее сообщение.

        Returns:
            BotResponse: Сообщение о неподдерживаемом формате.
        """

        reply_text = f"Формат сообщения {message.message_type} пока не поддерживается."

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=reply_text,
                )
            ]
        )

    def _ask_qa_service(self, question: str, context: str | None = None) -> dict:
        """Отправляет вопрос в QA-сервис и возвращает полный ответ.

        Args:
            question: Текст вопроса пользователя.
            context: История диалога или другой дополнительный контекст.

        Returns:
            dict: Ответ с ключами answer, expanded_query, keywords, model, sources, question_type.
        """
        from services.qa_service_client import (
            QAServiceTimeout,
            QAServiceUnavailable,
            QAServiceRateLimited,
            QAServiceError,
        )

        try:
            logger.info(
                f"Sending to QA: question='{question[:80]}', "
                f"context_len={len(context or '')}"
            )
            result = self._qa_service_client.ask(question=question, context=context)
            logger.info(
                f"QA response: answer_len={len(result.get('answer', ''))}, "
                f"type={result.get('question_type')}, "
                f"sources={len(result.get('sources', []))}"
            )
            return result
        except QAServiceTimeout:
            logger.error("QA service timeout")
            return {"answer": (
                "Не удалось быстро найти ответ. "
                "Попробуйте переформулировать вопрос — "
                "используйте простые термины и конкретные формулировки. "
                "Если не поможет, повторите чуть позже."
            )}
        except QAServiceUnavailable:
            logger.error("QA service unavailable")
            return {"answer": (
                "Сервис временно недоступен. "
                "Мы уже работаем над устранением проблемы. "
                "Попробуйте через пару минут."
            )}
        except QAServiceRateLimited:
            logger.error("QA service rate limited")
            return {"answer": (
                "Сервис сейчас перегружен запросами. "
                "Попробуйте повторить вопрос чуть позже."
            )}
        except QAServiceError as e:
            logger.error(f"QA service error: {e}")
            return {"answer": (
                "Не удалось сформировать ответ. "
                "Попробуйте переформулировать вопрос — "
                "используйте простые термины и конкретные формулировки."
            )}
        except Exception as e:
            logger.error(f"Unexpected QA error: {e}")
            return {"answer": (
                "Что-то пошло не так. "
                "Попробуйте повторить запрос позже или переформулировать вопрос."
            )}

    def _format_qa_answer(self, qa_result: dict) -> str:
        """Форматирует ответ QA для отправки в мессенджер.

        Добавляет блок "Подробнее:" с ссылками из sources.
        Удаляет оставшийся markdown (safety-net).
        Обрезает слишком длинные ответы.

        Args:
            qa_result: Ответ от QA-сервиса.

        Returns:
            str: Отформатированный ответ.
        """
        answer = qa_result.get("answer", "")
        sources = qa_result.get("sources", [])

        answer = self._strip_remaining_markdown(answer)

        if sources:
            link_lines = [f"Подробнее: {url}" for url in sources[:3]]
            answer = f"{answer}\n\n" + "\n".join(link_lines)

        if len(answer) > 3900:
            answer = answer[:3850] + "\n\n..."

        return answer

    def _strip_remaining_markdown(self, text: str) -> str:
        """Удалить оставшийся markdown (safety-net после qa-service)."""
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _is_service_command(self, normalized_text: str) -> bool:
        """Определяет, является ли сообщение сервисной slash-командой.

        Args:
            normalized_text: Нормализованный текст сообщения.

        Returns:
            bool: `True`, если это сервисная команда.
        """

        return normalized_text.startswith("/")

    def _build_service_command_response(self) -> BotResponse:
        """Возвращает ответ для неподдерживаемой сервисной команды.

        Returns:
            BotResponse: Сервисный ответ без сохранения в историю.
        """

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text="Эта команда пока не поддерживается.",
                )
            ]
        )

    def _build_start_response(self, message: IncomingMessage, user) -> BotResponse:
        """Возвращает стартовое сообщение и базовые inline-кнопки.

        Args:
            message: Нормализованное входящее сообщение.
            user: Текущий пользователь из БД.

        Returns:
            BotResponse: Ответ для команды `/start`.
        """

        is_subscribed = bool(user.is_subscribed) if user is not None else False

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    parse_mode="HTML",
                    text=(
                        "Привет! 👋🏻 Я бот-помощник Вопрошалыч.\n\n"
                        "Я отвечаю на вопросы об обучении в ТюмГУ — "
                        "расписание, стипендии, общежития, документы, "
                        "карты доступа и многое другое.\n\n"
                        "Источники информации:\n"
                        "• <a href=\"https://utmn.ru\">Официальный сайт ТюмГУ</a>\n"
                        "• <a href=\"https://sveden.utmn.ru\">Сведения об образовательной организации</a>\n"
                        "• <a href=\"https://confluence.utmn.ru/pages/viewpage.action?pageId=3607500\">Инструкции для ИС ТюмГУ</a>\n"
                        "• <a href=\"https://confluence.utmn.ru/pages/viewpage.action?pageId=86478972\">Руководства для обучающихся</a>\n\n"
                        "Кнопка «Начать новый диалог» сбрасывает историю общения — "
                        "я начну отвечать без учёта предыдущих вопросов.\n\n"
                        "Подписка на поздравления с праздниками доступна "
                        "через кнопку ниже!\n\n"
                        "Ответы формируются с помощью искусственного интеллекта "
                        "и могут содержать неточности. Продолжая работу с ботом, "
                        "вы даёте согласие на обработку персональных данных "
                        "и получение сообщений."
                    ),
                    buttons=self._build_start_buttons(is_subscribed),
                    reply_keyboard=self._build_main_keyboard(),
                )
            ]
        )

    def _build_help_response(self) -> BotResponse:
        """Возвращает справочное сообщение с контактами.

        Returns:
            BotResponse: Ответ для команды `/help`.
        """

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=(
                        "📋 Контакты:\n\n"
                        "Единый деканат:\n"
                        "г. Тюмень, ул. Ленина, 16\n"
                        "Тел.: 8 (3452) 59-74-29\n"
                        "Email: ed@utmn.ru\n\n"
                        "Приёмная комиссия:\n"
                        "Тел.: 8-800-700-05-53\n"
                        "Email: 597759@utmn.ru\n\n"
                        "Техподдержка Вопрошалыча:\n"
                        "Email: stud0000122686@utmn.ru\n\n"
                        "Также вы можете задать вопрос прямо здесь — "
                        "я отвечу на основе базы знаний ТюмГУ."
                    ),
                )
            ]
        )

    def _build_start_buttons(self, is_subscribed: bool) -> list[list[InlineButton]]:
        """Возвращает inline-кнопки стартового сообщения.

        Args:
            is_subscribed: Текущий статус подписки.

        Returns:
            list[list[InlineButton]]: Кнопки стартового сообщения.
        """

        subscription_text = (
            "Отписаться от рассылки" if is_subscribed else "Подписаться на рассылку"
        )

        return [
            [
                InlineButton(
                    text="Начать новый диалог",
                    callback_data="dialog:start_new",
                )
            ],
            [
                InlineButton(
                    text=subscription_text,
                    callback_data="subscription:toggle",
                )
            ],
        ]

    def _build_main_keyboard(self) -> list[list[KeyboardButton]]:
        """Возвращает постоянную reply-клавиатуру под полем ввода.

        Returns:
            list[list[KeyboardButton]]: Кнопки для быстрого доступа.
        """

        return [
            [KeyboardButton(text="📋 Помощь")],
            [KeyboardButton(text="🔄 Новый диалог")],
            [KeyboardButton(text="🔔 Рассылка")],
        ]

    def _build_feedback_buttons(self) -> list[list[InlineButton]]:
        """Возвращает inline-кнопки для оценки ответа.

        Returns:
            list[list[InlineButton]]: Кнопки лайка, дизлайка и нового диалога.
        """

        return [
            [
                InlineButton(text="❤️", callback_data="feedback:like"),
                InlineButton(text="👎", callback_data="feedback:dislike"),
            ],
            [
                InlineButton(text="🔄 Новый диалог", callback_data="dialog:start_new"),
            ],
        ]
