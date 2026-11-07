import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from src.modules.reminders.domain.enums import (
    CurrencyCode,
    MedicationLogStatus,
    Priority,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)


class ReminderActionType(enum.StrEnum):
    """Типи інтерактивних дій користувача над нагадуванням."""

    COMPLETE = "COMPLETE"
    SNOOZE = "SNOOZE"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    RECORD_PAYMENT = "RECORD_PAYMENT"
    RECORD_MEDICATION_INTAKE = "RECORD_MEDICATION_INTAKE"


class CreateReminderCommand(BaseModel):
    """Вхідна команда створення нового нагадування будь-якого з 5 типів."""

    reminder_type: Annotated[
        ReminderType,
        Field(description="Тип створюваного нагадування"),
    ]
    schedule_logic: Annotated[
        ScheduleLogicType,
        Field(description="Логіка планування розкладу"),
    ]
    title: Annotated[
        str,
        Field(min_length=1, max_length=255, description="Назва або короткий зміст нагадування"),
    ]
    description: Annotated[
        str | None,
        Field(default=None, description="Розширений опис або додаткова примітка"),
    ] = None
    schedule_config: Annotated[
        dict[str, Any],
        Field(description="Параметри конфігурації розкладу для обраної логіки"),
    ]
    lead_times: Annotated[
        list[str],
        Field(description="Масив інтервалів завчасних сповіщень (наприклад ['7d', '1d', '0d'])"),
    ] = []

    # Специфічні поля: Задачі
    due_datetime: Annotated[
        datetime | None,
        Field(default=None, description="Крайній термін виконання (дедлайн) у UTC"),
    ] = None
    base_priority: Annotated[
        Priority | None,
        Field(default=None, description="Базовий пріоритет задачі"),
    ] = None

    # Специфічні поля: Підписки
    regular_amount: Annotated[
        Decimal | None,
        Field(default=None, ge=Decimal("0.00"), description="Регулярна сума платежу"),
    ] = None
    currency: Annotated[
        CurrencyCode,
        Field(default=CurrencyCode.UAH, description="Валюта розрахунків підписки"),
    ] = CurrencyCode.UAH
    is_trial: Annotated[
        bool,
        Field(default=False, description="Прапорець безкоштовного пробного періоду (Trial)"),
    ] = False
    trial_end_date: Annotated[
        date | None,
        Field(default=None, description="Дата завершення пробного періоду"),
    ] = None
    discount_amount: Annotated[
        Decimal | None,
        Field(default=None, ge=Decimal("0.00"), description="Акційна знижена вартість підписки"),
    ] = None
    discount_cycles_total: Annotated[
        int | None,
        Field(default=None, gt=0, description="Загальна кількість циклів зі знижкою"),
    ] = None
    discount_cycles_remaining: Annotated[
        int | None,
        Field(default=None, ge=0, description="Залишкова кількість циклів за зниженою ціною"),
    ] = None

    # Специфічні поля: Ліки
    course_duration_days: Annotated[
        int | None,
        Field(default=None, gt=0, description="Тривалість курсу лікування у днях"),
    ] = None
    medication_start_date: Annotated[
        date | None,
        Field(default=None, description="Дата початку прийому препарату"),
    ] = None
    medication_end_date: Annotated[
        date | None,
        Field(default=None, description="Дата завершення курсу лікування"),
    ] = None
    strict_schedule: Annotated[
        bool,
        Field(default=False, description="Суворий графік прийому (ігнорування тихих годин)"),
    ] = False


class UpdateReminderCommand(BaseModel):
    """Вхідна команда повного перезапису нагадування (HTTP PUT Full Update)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Поточна версія запису для оптимістичного блокування (OCC)"),
    ]
    schedule_logic: Annotated[
        ScheduleLogicType,
        Field(description="Логіка планування розкладу"),
    ]
    title: Annotated[
        str,
        Field(min_length=1, max_length=255, description="Назва або короткий зміст нагадування"),
    ]
    description: Annotated[
        str | None,
        Field(default=None, description="Розширений опис або додаткова примітка"),
    ] = None
    schedule_config: Annotated[
        dict[str, Any],
        Field(description="Параметри конфігурації розкладу для обраної логіки"),
    ]
    lead_times: Annotated[
        list[str],
        Field(description="Масив інтервалів завчасних сповіщень"),
    ] = []
    status: Annotated[
        ReminderStatus,
        Field(default=ReminderStatus.ACTIVE, description="Статус нагадування"),
    ] = ReminderStatus.ACTIVE

    # Специфічні поля: Задачі
    due_datetime: Annotated[
        datetime | None,
        Field(default=None, description="Крайній термін виконання (дедлайн) у UTC"),
    ] = None
    base_priority: Annotated[
        Priority | None,
        Field(default=None, description="Базовий пріоритет задачі"),
    ] = None

    # Специфічні поля: Підписки
    regular_amount: Annotated[
        Decimal | None,
        Field(default=None, ge=Decimal("0.00"), description="Регулярна сума платежу"),
    ] = None
    currency: Annotated[
        CurrencyCode | None,
        Field(default=None, description="Валюта підписки"),
    ] = None
    is_trial: Annotated[
        bool,
        Field(default=False, description="Прапорець пробного періоду"),
    ] = False
    trial_end_date: Annotated[
        date | None,
        Field(default=None, description="Дата завершення пробного періоду"),
    ] = None
    discount_amount: Annotated[
        Decimal | None,
        Field(default=None, ge=Decimal("0.00"), description="Акційна сума підписки"),
    ] = None
    discount_cycles_total: Annotated[
        int | None,
        Field(default=None, gt=0, description="Загальна кількість акційних циклів"),
    ] = None
    discount_cycles_remaining: Annotated[
        int | None,
        Field(default=None, ge=0, description="Залишкова кількість акційних циклів"),
    ] = None

    # Специфічні поля: Ліки
    course_duration_days: Annotated[
        int | None,
        Field(default=None, gt=0, description="Тривалість курсу лікування у днях"),
    ] = None
    medication_start_date: Annotated[
        date | None,
        Field(default=None, description="Дата початку курсу лікування"),
    ] = None
    medication_end_date: Annotated[
        date | None,
        Field(default=None, description="Дата завершення курсу лікування"),
    ] = None
    strict_schedule: Annotated[
        bool,
        Field(default=False, description="Суворий графік прийому ліків"),
    ] = False


class PatchReminderCommand(BaseModel):
    """Вхідна команда точкового часткового оновлення нагадування (HTTP PATCH)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Поточна версія запису для оптимістичного блокування (OCC)"),
    ]
    title: Annotated[
        str | None,
        Field(default=None, min_length=1, max_length=255, description="Нова назва нагадування"),
    ] = None
    description: Annotated[
        str | None,
        Field(default=None, description="Новий розширений опис нагадування"),
    ] = None
    schedule_config: Annotated[
        dict[str, Any] | None,
        Field(default=None, description="Оновлена конфігурація розкладу"),
    ] = None
    lead_times: Annotated[
        list[str] | None,
        Field(default=None, description="Оновлений масив завчасних сповіщень"),
    ] = None

    # Специфічні поля: Задачі
    due_datetime: Annotated[
        datetime | None,
        Field(default=None, description="Оновлений дедлайн у UTC"),
    ] = None
    base_priority: Annotated[
        Priority | None,
        Field(default=None, description="Оновлений базовий пріоритет"),
    ] = None

    # Специфічні поля: Підписки
    regular_amount: Annotated[
        Decimal | None,
        Field(default=None, ge=Decimal("0.00"), description="Оновлена регулярна сума"),
    ] = None
    currency: Annotated[
        CurrencyCode | None,
        Field(default=None, description="Оновлена валюта"),
    ] = None
    is_trial: Annotated[
        bool | None,
        Field(default=None, description="Оновлений прапорець пробного періоду"),
    ] = None
    trial_end_date: Annotated[
        date | None,
        Field(default=None, description="Оновлена дата завершення тріалу"),
    ] = None
    discount_amount: Annotated[
        Decimal | None,
        Field(default=None, ge=Decimal("0.00"), description="Оновлена акційна сума"),
    ] = None
    discount_cycles_total: Annotated[
        int | None,
        Field(default=None, gt=0, description="Оновлена кількість акційних циклів"),
    ] = None
    discount_cycles_remaining: Annotated[
        int | None,
        Field(default=None, ge=0, description="Оновлена залишкова кількість циклів"),
    ] = None

    # Специфічні поля: Ліки
    course_duration_days: Annotated[
        int | None,
        Field(default=None, gt=0, description="Оновлена тривалість курсу у днях"),
    ] = None
    medication_start_date: Annotated[
        date | None,
        Field(default=None, description="Оновлена дата початку курсу"),
    ] = None
    medication_end_date: Annotated[
        date | None,
        Field(default=None, description="Оновлена дата завершення курсу"),
    ] = None
    strict_schedule: Annotated[
        bool | None,
        Field(default=None, description="Оновлений прапорець суворого графіка"),
    ] = None


class ReminderActionCommand(BaseModel):
    """Вхідна команда для виконання інтерактивної дії над нагадуванням (RPC ендпоінт)."""

    action: Annotated[
        ReminderActionType,
        Field(description="Тип виконуваної дії (COMPLETE, SNOOZE, PAUSE тощо)"),
    ]
    snooze_minutes: Annotated[
        int,
        Field(default=15, ge=1, le=1440, description="Кількість хвилин для відкладення при дії SNOOZE"),
    ] = 15
    medication_status: Annotated[
        MedicationLogStatus | None,
        Field(default=None, description="Статус прийому ліків (TAKEN, SNOOZED, MISSED) для RECORD_MEDICATION_INTAKE"),
    ] = None
    scheduled_at: Annotated[
        datetime | None,
        Field(default=None, description="Запланований час прийому ліків у UTC"),
    ] = None


class SchedulerBatchResultDTO(BaseModel):
    """Звіт про результати виконання чергового щохвилинного батчу шедулера."""

    processed_count: Annotated[
        int,
        Field(ge=0, description="Загальна кількість оброблених нагадувань у поточному батчі"),
    ]
    notifications_queued: Annotated[
        int,
        Field(ge=0, description="Кількість сповіщень, доданих до черги відправки Redis"),
    ]
    deferred_to_quiet_hours: Annotated[
        int,
        Field(ge=0, description="Кількість нагадувань, перенесених на ранок через тихі години"),
    ]
    completed_or_converted: Annotated[
        int,
        Field(ge=0, description="Кількість завершених або конвертованих із тріалу нагадувань"),
    ]
