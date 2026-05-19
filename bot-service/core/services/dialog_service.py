"""Сервис для хранения и сборки контекста диалога."""

from __future__ import annotations

import json

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

    def build_context(self, session_id: int, max_messages: int = 3, max_chars: int = 300) -> str:
        """Собирает последние сообщения текущей сессии в текстовый контекст.

        Берёт до max_messages последних пар вопрос-ответ (сначала user, потом bot).
        Если суммарная длина превышает max_chars — обрезает начало, оставляя конец.

        Args:
            session_id: Идентификатор сессии.
            max_messages: Максимум пар вопрос-ответ (по умолчанию 3).
            max_chars: Максимум символов в контексте (по умолчанию 1500).

        Returns:
            str: Текст контекста или пустая строка.
        """

        session = get_session()
        try:
            messages = (
                session.query(DialogMessage)
                .filter(DialogMessage.session_id == session_id)
                .order_by(DialogMessage.id.desc())
                .limit(max_messages * 2)
                .all()
            )
            if not messages:
                return ""

            lines = []
            for msg in reversed(messages):
                role = "Пользователь" if msg.role == USER_ROLE else "Бот"
                content = msg.content or ""
                lines.append(f"{role}: {content}")

            full_text = "\n".join(lines)
            if len(full_text) <= max_chars:
                return full_text

            return full_text[len(full_text) - max_chars:]
        except Exception:
            session.rollback()
            return ""
        finally:
            session.close()

    def save_question_answer(
        self,
        session_id: int,
        question: str,
        answer: str,
        model_used: str | None = None,
        expanded_query: str | None = None,
        keywords: dict | None = None,
        question_type: int | None = None,
        normalized_context: str | None = None,
        relevance_type: str | None = None,
        relevant_sources: list[int] | None = None,
        source_links: list[dict] | None = None,
    ) -> tuple[DialogMessage | None, DialogMessage | None]:
        """Сохраняет пару вопрос-ответ в историю и связывает их между собой.

        Args:
            session_id: Идентификатор активной сессии.
            question: Текст вопроса пользователя.
            answer: Текст ответа бота.
            model_used: Идентификатор модели, если он известен.
            expanded_query: Расширенный/исправленный запрос от LLM.
            keywords: Извлечённые ключевые слова (high_level, low_level).
            question_type: Тип вопроса (1=БЗ, 2=система, 3=общий).
            normalized_context: Нормализованный контекст для поиска.
            relevance_type: Релевантность ответа для БЗ: a=отвечено, b=нет информации.
            relevant_sources: Список релевантных источников.
            source_links: URL источников, которые были показаны пользователю.

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
                normalized_query=expanded_query,
                question_type=question_type,
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

            keywords_json = json.dumps(keywords, ensure_ascii=False) if keywords else None
            relevant_sources_json = json.dumps(relevant_sources, ensure_ascii=False) if relevant_sources else None
            source_links_json = json.dumps(source_links, ensure_ascii=False) if source_links else None

            session.add(
                QuestionAnswerLink(
                    question_id=question_message.id,
                    answer_id=answer_message.id,
                    expanded_query=expanded_query,
                    keywords=keywords_json,
                    normalized_context=normalized_context,
                    relevance_type=relevance_type,
                    relevant_sources=relevant_sources_json,
                    source_links=source_links_json,
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
