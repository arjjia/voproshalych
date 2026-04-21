"""Общие выходные модели, которые возвращает core-сервис бота."""

from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Поддерживаемые типы действий, которые возвращает core."""

    send_text = "send_text"


class InlineButton(BaseModel):
    """Inline-кнопка, которую должен показать адаптер платформы.

    Attributes:
        text: Текст на кнопке.
        callback_data: Данные callback-события.
    """

    text: str = Field(..., description="Текст кнопки")
    callback_data: str = Field(..., description="Данные callback-события")


class KeyboardButton(BaseModel):
    """Кнопка reply-клавиатуры (отправляет текстовое сообщение).

    Attributes:
        text: Текст на кнопке (он же отправляется как сообщение).
    """

    text: str = Field(..., description="Текст кнопки")


class OutgoingAction(BaseModel):
    """Действие, которое должен выполнить адаптер платформы.

    Attributes:
        type: Тип действия, понятный платформенным адаптерам.
        text: Текстовая нагрузка для текстовых действий.
        buttons: Inline-кнопки для отображения под сообщением.
        reply_keyboard: Постоянная клавиатура под полем ввода.
    """

    type: ActionType
    text: str | None = Field(
        default=None,
        description="Текстовая нагрузка для текстовых действий",
    )
    buttons: list[list[InlineButton]] = Field(
        default_factory=list,
        description="Inline-кнопки для платформенных адаптеров",
    )
    reply_keyboard: list[list[KeyboardButton]] = Field(
        default_factory=list,
        description="Постоянная reply-клавиатура под полем ввода",
    )


class BotResponse(BaseModel):
    """Ответ слоя бизнес-логики core."""

    actions: list[OutgoingAction] = Field(default_factory=list)
