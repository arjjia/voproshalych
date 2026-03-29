"""Сервис для хранения и сборки контекста диалога."""

from __future__ import annotations

from sqlalchemy.sql import func

from db import DialogMessage, DialogSession, QuestionAnswerLink, get_session


ACTIVE_SESSION_STATES = {"START", "DIALOG", "WAITING_ANSWER"}
CLOSED_SESSION_STATE = "CLOSED"
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"


class DialogService:
    """Управляет сессиями, историей сообщений и контекстом диалога."""

    def get_or_create_active_session(self, user_id: int) -> DialogSession | None:
        """Возвращает активную сессию пользователя или создает новую.

        Args:
            user_id: Идентификатор пользователя в БД.

        Returns:
            DialogSession | None: Активная сессия или `None` при ошибке.
        """

        session = get_session()
        try:
            dialog_session = (
                session.query(DialogSession)
                .filter(
                    DialogSession.user_id == user_id,
                    DialogSession.state.in_(ACTIVE_SESSION_STATES),
                )
                .order_by(DialogSession.id.desc())
                .one_or_none()
            )
            if dialog_session is None:
                dialog_session = DialogSession(user_id=user_id, state="DIALOG")
                session.add(dialog_session)
                session.commit()
                session.refresh(dialog_session)
                return dialog_session

            if dialog_session.state != "DIALOG":
                dialog_session.state = "DIALOG"
                session.commit()
                session.refresh(dialog_session)

            return dialog_session
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def start_new_dialog(self, user_id: int) -> DialogSession | None:
        """Закрывает предыдущие сессии и создает новый диалог.

        Args:
            user_id: Идентификатор пользователя в БД.

        Returns:
            DialogSession | None: Новая активная сессия или `None` при ошибке.
        """

        session = get_session()
        try:
            (
                session.query(DialogSession)
                .filter(
                    DialogSession.user_id == user_id,
                    DialogSession.state.in_(ACTIVE_SESSION_STATES),
                )
                .update({"state": CLOSED_SESSION_STATE}, synchronize_session=False)
            )

            dialog_session = DialogSession(user_id=user_id, state="DIALOG")
            session.add(dialog_session)
            session.commit()
            session.refresh(dialog_session)
            return dialog_session
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def build_context(self, session_id: int, limit: int) -> str:
        """Собирает последние сообщения текущей сессии в текстовый контекст.

        Args:
            session_id: Идентификатор сессии.
            limit: Максимальное количество сообщений в контексте.

        Returns:
            str: Текст контекста или пустая строка.
        """

        session = get_session()
        try:
            messages = (
                session.query(DialogMessage)
                .filter(DialogMessage.session_id == session_id)
                .order_by(DialogMessage.id.desc())
                .limit(limit)
                .all()
            )
            if not messages:
                return ""

            lines = []
            for message in reversed(messages):
                role = "Пользователь" if message.role == USER_ROLE else "Бот"
                lines.append(f"{role}: {message.content}")
            return "\n".join(lines)
        finally:
            session.close()

    def save_question_answer(
        self,
        session_id: int,
        question: str,
        answer: str,
        model_used: str | None = None,
    ) -> tuple[DialogMessage | None, DialogMessage | None]:
        """Сохраняет пару вопрос-ответ в историю и связывает их между собой.

        Args:
            session_id: Идентификатор активной сессии.
            question: Текст вопроса пользователя.
            answer: Текст ответа бота.
            model_used: Идентификатор модели, если он известен.

        Returns:
            tuple[DialogMessage | None, DialogMessage | None]:
                Сообщения вопроса и ответа.
        """

        session = get_session()
        try:
            question_message = DialogMessage(
                session_id=session_id,
                role=USER_ROLE,
                content=question,
            )
            answer_message = DialogMessage(
                session_id=session_id,
                role=ASSISTANT_ROLE,
                content=answer,
                model_used=model_used,
            )
            session.add(question_message)
            session.add(answer_message)
            session.flush()

            session.add(
                QuestionAnswerLink(
                    question_id=question_message.id,
                    answer_id=answer_message.id,
                )
            )
            (
                session.query(DialogSession)
                .filter(DialogSession.id == session_id)
                .update(
                    {
                        "last_message_at": func.now(),
                        "state": "DIALOG",
                    },
                    synchronize_session=False,
                )
            )

            session.commit()
            session.refresh(question_message)
            session.refresh(answer_message)
            return question_message, answer_message
        except Exception:
            session.rollback()
            return None, None
        finally:
            session.close()
