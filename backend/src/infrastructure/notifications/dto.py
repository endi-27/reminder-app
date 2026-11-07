import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationEventType(enum.StrEnum):
    """Типи подій сповіщень у системі нагадувань."""

    REMINDER_DUE = "REMINDER_DUE"
    TRIAL_EXPIRED = "TRIAL_EXPIRED"
    DAILY_DIGEST = "DAILY_DIGEST"


class DigestTaskItemDTO(BaseModel):
    """Елемент відкритої справи для формування щоденного дайджесту."""

    reminder_id: Annotated[UUID, Field(description="UUIDv7 відкритої задачі")]
    title: Annotated[str, Field(min_length=1, max_length=255, description="Назва відкритої задачі")]
    description: Annotated[str | None, Field(default=None, description="Опис задачі")] = None
    priority: Annotated[str | None, Field(default=None, description="Пріоритет задачі")] = None


class NotificationPayload(BaseModel):
    """Чистий DTO даних події сповіщення для передачі через чергу Redis до клієнтського бота."""

    event_type: Annotated[
        NotificationEventType,
        Field(default=NotificationEventType.REMINDER_DUE, description="Тип події сповіщення"),
    ] = NotificationEventType.REMINDER_DUE
    recipient_channel: Annotated[
        str,
        Field(default="telegram", description="Канал доставки сповіщення"),
    ] = "telegram"
    recipient_chat_id: Annotated[
        int,
        Field(description="Ідентифікатор чату отримувача в месенджері"),
    ]
    user_timezone: Annotated[
        str,
        Field(default="Europe/Kyiv", description="Часовий пояс користувача (IANA)"),
    ] = "Europe/Kyiv"
    disable_sound: Annotated[
        bool,
        Field(default=False, description="Відправити сповіщення без звуку"),
    ] = False

    # Дані конкретного нагадування (для REMINDER_DUE та TRIAL_EXPIRED)
    reminder_id: Annotated[
        UUID | None,
        Field(default=None, description="UUIDv7 нагадування (для REMINDER_DUE та TRIAL_EXPIRED)"),
    ] = None
    reminder_type: Annotated[
        str | None,
        Field(default=None, description="Тип нагадування"),
    ] = None
    title: Annotated[
        str | None,
        Field(default=None, description="Назва нагадування"),
    ] = None
    description: Annotated[
        str | None,
        Field(default=None, description="Опис нагадування"),
    ] = None

    # Дані для задач (DEADLINE_TASK / OPEN_TASK)
    due_datetime: Annotated[
        datetime | None,
        Field(default=None, description="Дедлайн задачі в UTC"),
    ] = None
    effective_priority: Annotated[
        str | None,
        Field(default=None, description="Розрахований або базовий пріоритет"),
    ] = None

    # Дані для підписок (SUBSCRIPTION)
    amount: Annotated[
        Decimal | None,
        Field(default=None, description="Сума платежу підписки"),
    ] = None
    currency: Annotated[
        str | None,
        Field(default=None, description="Валюта платежу підписки"),
    ] = None
    converted_amount_uah: Annotated[
        Decimal | None,
        Field(default=None, description="Еквівалент у гривні за курсом банку"),
    ] = None
    rate_provider: Annotated[
        str | None,
        Field(default=None, description="Банк, за курсом якого виконано конвертацію"),
    ] = None
    is_stale_rate_fallback: Annotated[
        bool,
        Field(default=False, description="Чи використано резервний курс НБУ через застарілість"),
    ] = False
    is_trial: Annotated[
        bool,
        Field(default=False, description="Ознака пробного періоду підписки"),
    ] = False
    is_last_discount_cycle: Annotated[
        bool,
        Field(default=False, description="Ознака останнього акційного циклу підписки"),
    ] = False

    # Дані для ліків (MEDICATION)
    medication_end_date: Annotated[
        date | None,
        Field(default=None, description="Дата завершення курсу ліків"),
    ] = None
    strict_schedule: Annotated[
        bool,
        Field(default=False, description="Суворий графік прийому ліків"),
    ] = False

    # Дані для річниць (ANNIVERSARY)
    calculated_age: Annotated[
        int | None,
        Field(default=None, description="Розрахований вік або кількість років річниці"),
    ] = None

    # Список відкритих справ для щоденного дайджесту (DAILY_DIGEST)
    digest_tasks: Annotated[
        list[DigestTaskItemDTO],
        Field(description="Список відкритих справ для щоденного дайджесту"),
    ] = []
