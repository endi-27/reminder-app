from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.reminders.domain.enums import (
    MedicationLogStatus,
    Priority,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)


class ReminderResponseDTO(BaseModel):
    """Вихідний DTO повних даних нагадування для Read-операцій (CQRS)."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[UUID, Field(description="Унікальний ідентифікатор нагадування (UUIDv7)")]
    user_id: Annotated[UUID, Field(description="Ідентифікатор власника нагадування")]
    reminder_type: Annotated[ReminderType, Field(description="Тип нагадування")]
    schedule_logic: Annotated[ScheduleLogicType, Field(description="Логіка планування розкладу")]
    title: Annotated[str, Field(description="Назва або короткий зміст нагадування")]
    description: Annotated[str | None, Field(default=None, description="Розширений опис або примітка")] = None
    status: Annotated[ReminderStatus, Field(description="Статус життєвого циклу нагадування")]
    next_trigger_at: Annotated[datetime, Field(description="Наступний момент спрацювання (UTC)")]
    schedule_config: Annotated[dict[str, Any], Field(description="Конфігурація параметрів розкладу")]
    lead_times: Annotated[list[str], Field(description="Масив завчасних сповіщень")]
    created_at: Annotated[datetime, Field(description="Часова мітка створення (UTC)")]
    updated_at: Annotated[datetime, Field(description="Часова мітка останнього оновлення (UTC)")]
    version: Annotated[int, Field(description="Версія запису для оптимістичного блокування OCC")]

    # Специфічні поля: Задачі
    due_datetime: Annotated[
        datetime | None,
        Field(default=None, description="Крайній термін виконання (дедлайн) у UTC"),
    ] = None
    base_priority: Annotated[
        Priority | None,
        Field(default=None, description="Базовий пріоритет задачі"),
    ] = None
    calculated_priority: Annotated[
        Priority | None,
        Field(default=None, description="Динамічно розрахований пріоритет"),
    ] = None

    # Специфічні поля: Підписки
    regular_amount: Annotated[
        Decimal | None,
        Field(default=None, description="Регулярна вартість підписки"),
    ] = None
    currency: Annotated[
        str | None,
        Field(default=None, description="Код валюти розрахунків"),
    ] = None
    is_trial: Annotated[
        bool,
        Field(default=False, description="Прапорець безкоштовного пробного періоду"),
    ] = False
    trial_end_date: Annotated[
        date | None,
        Field(default=None, description="Дата завершення пробного періоду"),
    ] = None
    discount_amount: Annotated[
        Decimal | None,
        Field(default=None, description="Акційна знижена вартість"),
    ] = None
    discount_cycles_total: Annotated[
        int | None,
        Field(default=None, description="Загальна кількість акційних циклів"),
    ] = None
    discount_cycles_remaining: Annotated[
        int | None,
        Field(default=None, description="Залишкова кількість циклів зі знижкою"),
    ] = None

    # Специфічні поля: Ліки
    course_duration_days: Annotated[
        int | None,
        Field(default=None, description="Тривалість курсу лікування у днях"),
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


class MedicationIntakeLogResponseDTO(BaseModel):
    """Вихідний DTO запису в журналі прийому медикаментів."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[UUID, Field(description="Унікальний ідентифікатор запису журналу")]
    reminder_id: Annotated[UUID, Field(description="Ідентифікатор нагадування про прийом ліків")]
    scheduled_at: Annotated[datetime, Field(description="Запланований час прийому (UTC)")]
    recorded_at: Annotated[datetime | None, Field(default=None, description="Фактичний час фіксації (UTC)")] = None
    status: Annotated[MedicationLogStatus, Field(description="Статус прийому ліків")]
    created_at: Annotated[datetime, Field(description="Часова мітка створення запису (UTC)")]
    version: Annotated[int, Field(description="Версія запису (OCC)")]


class MedicationAdherenceStatsDTO(BaseModel):
    """Зведена статистика комплаєнсу та дотримання графіку прийому лікарських засобів."""

    reminder_id: Annotated[UUID, Field(description="Ідентифікатор нагадування про ліки")]
    total_logs: Annotated[int, Field(ge=0, description="Загальна кількість зафіксованих подій")]
    taken_count: Annotated[int, Field(ge=0, description="Кількість успішних прийомів")]
    snoozed_count: Annotated[int, Field(ge=0, description="Кількість відкладень прийому ліків")]
    missed_count: Annotated[int, Field(ge=0, description="Кількість пропущених прийомів")]
    adherence_rate_percent: Annotated[
        float,
        Field(ge=0.0, le=100.0, description="Відсоток комплаєнсу (успішно прийнятих доз)"),
    ]
    logs: Annotated[
        list[MedicationIntakeLogResponseDTO],
        Field(description="Список останніх записів журналу"),
    ]
