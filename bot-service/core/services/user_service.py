"""Сервис для работы с пользователями бота."""

from __future__ import annotations

from sqlalchemy.sql import func

from db import Subscription, User, get_session
from models.callback import CallbackEvent
from models.message import IncomingMessage


def _user_identity_from_metadata(metadata: dict) -> tuple[str | None, str | None, str | None]:
    """Нормализует отображаемые поля пользователя из metadata разных платформ."""

    username = metadata.get("username") or metadata.get("sender_name")
    first_name = metadata.get("first_name")
    last_name = metadata.get("last_name")
    return username, first_name, last_name


class UserService:
    """Создает и обновляет пользователей в базе данных."""

    def upsert_user(self, message: IncomingMessage) -> User | None:
        """Создает или обновляет пользователя по входящему сообщению.

        Args:
            message: Нормализованное сообщение пользователя.

        Returns:
            User | None: Сохраненный пользователь или `None` при ошибке.
        """

        session = get_session()
        try:
            user = (
                session.query(User)
                .filter(
                    User.platform == message.platform.value,
                    User.platform_user_id == message.user_id,
                )
                .one_or_none()
            )

            metadata = message.metadata or {}
            username, first_name, last_name = _user_identity_from_metadata(metadata)
            if user is None:
                user = User(
                    platform=message.platform.value,
                    platform_user_id=message.user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                )
                session.add(user)
            else:
                user.username = username or user.username
                user.first_name = first_name or user.first_name
                user.last_name = last_name or user.last_name
                user.updated_at = func.now()

            session.commit()
            session.refresh(user)
            return user
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def get_user(self, platform: str, platform_user_id: str) -> User | None:
        """Возвращает пользователя по платформе и идентификатору.

        Args:
            platform: Платформа пользователя.
            platform_user_id: Идентификатор пользователя на платформе.

        Returns:
            User | None: Пользователь или `None`.
        """

        session = get_session()
        try:
            return (
                session.query(User)
                .filter(
                    User.platform == platform,
                    User.platform_user_id == platform_user_id,
                )
                .one_or_none()
            )
        finally:
            session.close()

    def toggle_subscription(self, event: CallbackEvent) -> User | None:
        """Переключает флаг подписки пользователя.

        Args:
            event: Callback-событие платформы.

        Returns:
            User | None: Обновленный пользователь или `None`.
        """

        session = get_session()
        try:
            user = (
                session.query(User)
                .filter(
                    User.platform == event.platform.value,
                    User.platform_user_id == event.user_id,
                )
                .one_or_none()
            )
            if user is None:
                return None

            if user.is_subscribed:
                active_subscription = (
                    session.query(Subscription)
                    .filter(
                        Subscription.user_id == user.id,
                        Subscription.unsubscribed_at.is_(None),
                    )
                    .order_by(Subscription.id.desc())
                    .one_or_none()
                )
                if active_subscription is not None:
                    active_subscription.unsubscribed_at = func.now()
                user.is_subscribed = False
            else:
                session.add(Subscription(user_id=user.id))
                user.is_subscribed = True

            user.updated_at = func.now()
            session.commit()
            session.refresh(user)
            return user
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()
