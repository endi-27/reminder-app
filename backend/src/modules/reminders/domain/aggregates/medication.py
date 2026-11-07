from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from uuid6 import uuid7

from src.core.domain import AggregateRoot
from src.modules.reminders.domain.aggregates.base import BaseReminder
from src.modules.reminders.domain.enums import (
    MedicationLogStatus,
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.domain.value_objects import QuietHoursWindow


@dataclass(kw_only=True)
class MedicationIntakeLog(AggregateRoot):
    """
    Доменний агрегат запису в журналі дотримання лікування (Adherence Log).
    Фіксує факт запланованого та фактичного прийому медикаментів.
    """

    reminder_id: UUID
    scheduled_at: datetime
    recorded_at: datetime | None = None
    status: MedicationLogStatus = MedicationLogStatus.MISSED

    def __post_init__(self) -> None:
        """Нормалізує часові мітки запису журналу до UTC."""
        if self.scheduled_at.tzinfo is None:
            self.scheduled_at = self.scheduled_at.replace(tzinfo=UTC)
        else:
            self.scheduled_at = self.scheduled_at.astimezone(UTC)

        if self.recorded_at is not None:
            if self.recorded_at.tzinfo is None:
                self.recorded_at = self.recorded_at.replace(tzinfo=UTC)
            else:
                self.recorded_at = self.recorded_at.astimezone(UTC)


@dataclass(kw_only=True)
class MedicationReminder(BaseReminder):
    """
    Доменний агрегат нагадування про прийом лікарських засобів.
    Підтримує як визначені курси (наприклад, 10 днів), так і безстроковий прийом (вітаміни, хронічні препарати),
    а також суворий графік (ігнорування тихих годин для життєво важливих ліків).
    """

    reminder_type: ReminderType = ReminderType.MEDICATION
    schedule_logic: ScheduleLogicType = ScheduleLogicType.DAILY_AT_TIMES
    course_duration_days: int | None = None
    medication_start_date: date | None = None
    medication_end_date: date | None = None
    strict_schedule: bool = False

    def __post_init__(self) -> None:
        """Автоматично обчислює дату завершення курсу ліків, якщо задано дату старту та тривалість."""
        super().__post_init__()

        if self.medication_start_date is not None and self.course_duration_days is not None:
            if self.medication_end_date is None:
                # Включний розрахунок: start_date + (N - 1) днів
                self.medication_end_date = self.medication_start_date + timedelta(days=self.course_duration_days - 1)
        elif self.course_duration_days is None:
            # Безстроковий або пожиттєвий прийом
            self.medication_end_date = None

    def record_intake(
        self,
        status: MedicationLogStatus,
        scheduled_at: datetime | None = None,
        recorded_at: datetime | None = None,
        user_timezone: str = "Europe/Kyiv",
        quiet_hours: QuietHoursWindow | None = None,
    ) -> MedicationIntakeLog:
        """
        Фіксує результат прийому ліків:
        - Створює запис у журналі MedicationIntakeLog.
        - При SNOOZED відкладає час спрацювання на +15 хвилин.
        - При TAKEN або MISSED перераховує наступний час прийому за розкладом (з урахуванням strict_schedule).
        - Якщо курс має фіксовану дату завершення і новий час перевищує її — переводить нагадування у COMPLETED.
        """
        self.ensure_active("зафіксувати прийом ліків деактивованого нагадування")

        sched = scheduled_at or self.next_trigger_at
        rec = recorded_at or datetime.now(UTC)

        log = MedicationIntakeLog(
            id=uuid7(),
            reminder_id=self.id,
            scheduled_at=sched,
            recorded_at=rec,
            status=status,
        )

        if status == MedicationLogStatus.SNOOZED:
            self.snooze(timedelta(minutes=15), now=rec)
        elif status in (MedicationLogStatus.TAKEN, MedicationLogStatus.MISSED):
            next_dt = self.advance_schedule(
                rec,
                user_timezone=user_timezone,
                quiet_hours=quiet_hours,
            )

            # Перевіряємо завершення курсу лікування
            if self.medication_end_date is not None:
                user_tz = ZoneInfo(user_timezone)
                next_local_date = next_dt.astimezone(user_tz).date()
                if next_local_date > self.medication_end_date:
                    self.complete()

        return log
