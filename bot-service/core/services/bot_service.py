"""Точка входа в бизнес-логику для обработки нормализованных сообщений."""

from config import settings
from models.callback import CallbackEvent
from models.message import IncomingMessage
from models.response import ActionType, BotResponse, InlineButton, OutgoingAction
from services.dialog_service import DialogService
from services.holiday_newsletter import HolidayNewsletterService
from services.qa_service_client import QAServiceClient
from services.user_service import UserService


class BotService:
    """Обрабатывает нормализованные сообщения и возвращает платформенно-независимые действия."""

    def __init__(self) -> None:
        """Инициализирует зависимости бизнес-логики."""

        self._qa_service_client = QAServiceClient(
            base_url=settings.qa_service_url,
            timeout_seconds=settings.qa_service_timeout_seconds,
        )
        self._dialog_service = DialogService()
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

        if event.callback_data == "subscription:toggle":
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
                            "Вы подписаны на праздничную рассылку."
                            if user.is_subscribed
                            else "Вы отписались от праздничной рассылки."
                        ),
                        buttons=self._build_start_buttons(user.is_subscribed),
                    )
                ]
            )

        if event.callback_data == "dialog:start_new":
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
                        text="Новый диалог начат. Можете отправить следующий вопрос.",
                    )
                ]
            )

        if event.callback_data == "feedback:like":
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text="Спасибо за положительную оценку.",
                    )
                ]
            )

        if event.callback_data == "feedback:dislike":
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text="Спасибо за оценку. Учту это в следующих ответах.",
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
        if lowered_text == "/ping":
            reply_text = "pong"
        elif self._is_service_command(lowered_text):
            return self._build_service_command_response()
        else:
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
            return self._ask_qa_service(question)

        dialog_session = self._dialog_service.get_or_create_active_session(user.id)
        if dialog_session is None:
            return self._ask_qa_service(question)

        history = self._dialog_service.build_context(
            session_id=dialog_session.id,
            limit=settings.dialog_context_limit_messages,
        )
        prompt = self._build_qa_question(question=question, history=history)
        reply_text = self._ask_qa_service(prompt)
        self._dialog_service.save_question_answer(
            session_id=dialog_session.id,
            question=question,
            answer=reply_text,
        )
        return reply_text

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

    def _ask_qa_service(self, question: str) -> str:
        """Отправляет вопрос в QA-сервис и возвращает ответ.

        Args:
            question: Текст вопроса пользователя.

        Returns:
            str: Ответ QA-сервиса или fallback-текст.
        """
        import logging

        from services.qa_service_client import (
            QAServiceTimeout,
            QAServiceUnavailable,
            QAServiceError,
        )

        logger = logging.getLogger(__name__)

        try:
            return self._qa_service_client.ask(question=question)
        except QAServiceTimeout:
            logger.error("QA service timeout")
            return (
                "Поиск ответа занимает дольше обычного. "
                "Попробуйте переформулировать вопрос или повторить позже."
            )
        except QAServiceUnavailable:
            logger.error("QA service unavailable")
            return (
                "Сервис временно недоступен. "
                "Мы уже работаем над устранением проблемы. Попробуйте через несколько минут."
            )
        except QAServiceError as e:
            logger.error(f"QA service error: {e}")
            return "Не удалось сформировать ответ. Попробуйте переформулировать вопрос."
        except Exception as e:
            logger.error(f"Unexpected QA error: {e}")
            return "Что-то пошло не так. Попробуйте повторить запрос позже."

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

    def _build_qa_question(self, question: str, history: str) -> str:
        """Собирает запрос для QA с учетом последних сообщений диалога.

        Args:
            question: Новый вопрос пользователя.
            history: История последних сообщений сессии.

        Returns:
            str: Текст запроса для QA-сервиса.
        """

        if not history:
            return question

        return (
            "Ниже история текущего диалога.\n"
            "Используй ее только как контекст для ответа на последний вопрос.\n\n"
            f"{history}\n\n"
            f"Последний вопрос пользователя: {question}"
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
                    text=(
                        "Привет! Я бот-помощник.\n\n"
                        "Сейчас я умею:\n"
                        "• отвечать на текстовые вопросы;\n"
                        "• принимать голосовые сообщения и готовиться к их "
                        "распознаванию;\n"
                        "• сохранять ваши настройки подписки на праздничную "
                        "рассылку.\n\n"
                        "Кнопка «Начать новый диалог» уже подготовлена и будет "
                        "использоваться для сброса истории общения.\n"
                        "Если хотите, можете сразу задать вопрос сообщением ниже."
                    ),
                    buttons=self._build_start_buttons(is_subscribed),
                )
            ]
        )

    def _build_start_buttons(self, is_subscribed: bool) -> list[list[InlineButton]]:
        """Возвращает кнопки стартового сообщения.

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

    def _build_feedback_buttons(self) -> list[list[InlineButton]]:
        """Возвращает inline-кнопки для оценки ответа.

        Returns:
            list[list[InlineButton]]: Кнопки лайка и дизлайка.
        """

        return [
            [
                InlineButton(text="👍", callback_data="feedback:like"),
                InlineButton(text="👎", callback_data="feedback:dislike"),
            ]
        ]
