from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import Field

from src.core.events.base import BaseEvent
from src.modules.reminders.domain.enums import CurrencyCode, MedicationLogStatus


class ReminderScheduledEvent(BaseEvent):
    """Подія планування або оновлення часу спрацювання нагадування шедулером."""

    reminder_id: Annotated[UUID, Field(description="Унікальний ідентифікатор нагадування")]
    user_id: Annotated[UUID, Field(description="Власник нагадування")]
    scheduled_at: Annotated[datetime, Field(description="Запланований точний час спрацювання (UTC)")]


class TrialExpiringSoonEvent(BaseEvent):
    """Подія наближення завершення безкоштовного пробного періоду підписки."""

    subscription_id: Annotated[UUID, Field(description="Унікальний ідентифікатор підписки")]
    user_id: Annotated[UUID, Field(description="Власник підписки")]
    days_left: Annotated[int, Field(description="Кількість днів до завершення тріалу")]
    next_charge_amount: Annotated[Decimal, Field(description="Сума першого регулярного списання")]
    currency: Annotated[CurrencyCode, Field(description="Валюта списання")]


class TrialConvertedToPaidEvent(BaseEvent):
    """Подія переходу підписки з пробного періоду в регулярний платний статус."""

    subscription_id: Annotated[UUID, Field(description="Унікальний ідентифікатор підписки")]
    user_id: Annotated[UUID, Field(description="Власник підписки")]
    first_billing_date: Annotated[date, Field(description="Дата першого регулярного списання")]


class SubscriptionDiscountExpiringSoonEvent(BaseEvent):
    """Подія наближення останнього акційного платежу зі знижкою."""

    subscription_id: Annotated[UUID, Field(description="Унікальний ідентифікатор підписки")]
    user_id: Annotated[UUID, Field(description="Власник підписки")]
    cycles_left: Annotated[int, Field(description="Кількість залишкових циклів зі знижкою")]
    regular_amount: Annotated[Decimal, Field(description="Майбутня регулярна вартість після завершення акції")]
    currency: Annotated[CurrencyCode, Field(description="Валюта платежу")]


class SubscriptionDiscountEndedEvent(BaseEvent):
    """Подія повного вичерпання акційних циклів та переходу на повну вартість."""

    subscription_id: Annotated[UUID, Field(description="Унікальний ідентифікатор підписки")]
    user_id: Annotated[UUID, Field(description="Власник підписки")]
    regular_amount: Annotated[Decimal, Field(description="Регулярна вартість підписки")]
    currency: Annotated[CurrencyCode, Field(description="Валюта платежу")]


class SubscriptionPaymentRecordedEvent(BaseEvent):
    """Подія фіксації чергової оплати підписки."""

    subscription_id: Annotated[UUID, Field(description="Унікальний ідентифікатор підписки")]
    user_id: Annotated[UUID, Field(description="Власник підписки")]
    paid_amount: Annotated[Decimal, Field(description="Фактично сплачена сума")]
    currency: Annotated[CurrencyCode, Field(description="Валюта")]
    next_trigger_at: Annotated[datetime, Field(description="Момент наступного списання (UTC)")]


class MedicationDueEvent(BaseEvent):
    """Подія настання часу прийому медичного препарату."""

    medication_id: Annotated[UUID, Field(description="Унікальний ідентифікатор нагадування ліків")]
    user_id: Annotated[UUID, Field(description="Власник нагадування")]
    title: Annotated[str, Field(description="Назва препарату та інструкція з дозування")]
    scheduled_at: Annotated[datetime, Field(description="Запланований час прийому (UTC)")]
    strict_schedule: Annotated[bool, Field(description="Ознака суворого графіку (ігнорування тихих годин)")]


class MedicationIntakeRecordedEvent(BaseEvent):
    """Подія фіксації користувачем прийому, відкладення або пропуску ліків."""

    medication_id: Annotated[UUID, Field(description="Унікальний ідентифікатор нагадування ліків")]
    user_id: Annotated[UUID, Field(description="Власник нагадування")]
    log_id: Annotated[UUID, Field(description="Ідентифікатор запису журналу прийому")]
    status: Annotated[MedicationLogStatus, Field(description="Зафіксований статус прийому")]


class MedicationCourseCompletedEvent(BaseEvent):
    """Подія успішного завершення призначеного курсу прийому медикаментів."""

    medication_id: Annotated[UUID, Field(description="Унікальний ідентифікатор нагадування ліків")]
    user_id: Annotated[UUID, Field(description="Власник нагадування")]


class TaskCompletedEvent(BaseEvent):
    """Подія завершення задачі користувачем."""

    task_id: Annotated[UUID, Field(description="Унікальний ідентифікатор задачі")]
    user_id: Annotated[UUID, Field(description="Власник задачі")]
    completed_at: Annotated[datetime, Field(description="Часова мітка виконання (UTC)")]
