"""Сервис для хранения и обновления оценок ответов бота."""

from __future__ import annotations

import logging

from db import DialogMessage, DialogSession, User, get_session
from services.user_service import UserService

logger = logging.getLogger(__name__)

FEEDBACK_LIKE = "like"
FEEDBACK_DISLIKE = "dislike"


class FeedbackService:
    """Управляет оценками ответов бота.

    Оценка привязывается к последнему ответу бота в активной сессии
    пользователя. При повторном нажатии той же кнопки — возвращается
    признак «уже оценено». При нажатии другой кнопки — оценка перезаписывается.
    """

    def __init__(self) -> None:
        self._user_service = UserService()

    def save_feedback(
        self,
        platform: str,
        platform_user_id: str,
        feedback_type: str,
    ) -> str | None:
        """Сохранить или обновить оценку последнего ответа бота.

        Args:
            platform: Платформа (telegram, vk, max).
            platform_user_id: ID пользователя на платформе.
            feedback_type: Тип оценки ('like' или 'dislike').

        Returns:
            None — оценка сохранена/обновлена.
            str — сообщение об ошибке или «уже оценено».
        """
        session = get_session()
        try:
            user = self._user_service.get_user(platform, platform_user_id)
            if user is None:
                return "Пользователь не найден."

            active_session = (
                session.query(DialogSession)
                .filter(
                    DialogSession.user_id == user.id,
                    DialogSession.state.in_(("START", "DIALOG", "WAITING_ANSWER")),
                )
                .order_by(DialogSession.id.desc())
                .first()
            )
            if active_session is None:
                return "Активный диалог не найден."

            last_answer = (
                session.query(DialogMessage)
                .filter(
                    DialogMessage.session_id == active_session.id,
                    DialogMessage.role == "assistant",
                )
                .order_by(DialogMessage.id.desc())
                .first()
            )
            if last_answer is None:
                return "Ответ не найден."

            if last_answer.feedback == feedback_type:
                return "already_rated"

            last_answer.feedback = feedback_type
            session.commit()
            return None
        except Exception:
            session.rollback()
            logger.exception("Failed to save feedback")
            return "Не удалось сохранить оценку."
        finally:
            session.close()
