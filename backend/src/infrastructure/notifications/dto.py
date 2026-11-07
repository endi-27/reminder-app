from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class ActionButton(BaseModel):
    """Модель інтерактивної інлайн-кнопки для сповіщення у месенджері."""

    text: Annotated[str, Field(min_length=1, max_length=64, description="Текст інлайн-кнопки в повідомленні")]
    callback_data: Annotated[
        str,
        Field(min_length=1, max_length=64, description="Дані зворотного виклику для обробника бота (до 64 байтів)"),
    ]


class NotificationPayload(BaseModel):
    """Спільний DTO для передачі сповіщень через чергу Redis до Telegram-бота."""

    recipient_channel: Annotated[
        str,
        Field(default="telegram", description="Канал доставки сповіщення"),
    ] = "telegram"
    recipient_chat_id: Annotated[
        int,
        Field(description="Ідентифікатор чату отримувача в Telegram"),
    ]
    reminder_id: Annotated[
        UUID | None,
        Field(default=None, description="UUID нагадування (опціонально для дайджестів)"),
    ] = None
    title: Annotated[
        str,
        Field(min_length=1, max_length=255, description="Заголовок сповіщення"),
    ]
    body: Annotated[
        str,
        Field(min_length=1, description="Форматований текст сповіщення"),
    ]
    buttons: Annotated[
        list[ActionButton],
        Field(description="Список інтерактивних кнопок швидких дій"),
    ] = []
    disable_sound: Annotated[
        bool,
        Field(default=False, description="Відправити сповіщення без звуку"),
    ] = False
