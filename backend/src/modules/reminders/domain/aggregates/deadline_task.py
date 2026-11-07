from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.reminders.domain.aggregates.base import BaseReminder
from src.modules.reminders.domain.enums import Priority, ReminderType, ScheduleLogicType
from src.modules.reminders.domain.services.schedule_calculator import ScheduleCalculator


@dataclass(kw_only=True)
class DeadlineTaskReminder(BaseReminder):
    """
    Доменний агрегат задачі з фіксованим дедлайном.
    Підтримує автоматичну динамічну ескалацію пріоритету залежно від наближення терміну виконання.
    """

    reminder_type: ReminderType = ReminderType.DEADLINE_TASK
    schedule_logic: ScheduleLogicType = ScheduleLogicType.EXACT_DATETIME_DEADLINE
    due_datetime: datetime
    base_priority: Priority | None = None
    calculated_priority: Priority | None = None

    def __post_init__(self) -> None:
        """Нормалізує часову мітку дедлайну до UTC та виконує базову валідацію."""
        super().__post_init__()

        if self.due_datetime.tzinfo is None:
            self.due_datetime = self.due_datetime.replace(tzinfo=UTC)
        else:
            self.due_datetime = self.due_datetime.astimezone(UTC)

    @property
    def effective_priority(self) -> Priority | None:
        """
        Результуючий пріоритет:
        Якщо користувач явно задав base_priority — він є вирішальним.
        Інакше повертається динамічно розрахований calculated_priority.
        """
        return self.base_priority or self.calculated_priority

    def recalculate_priority(
        self,
        now: datetime | None = None,
        *,
        auto_escalate: bool = True,
    ) -> Priority | None:
        """
        Оновлює поле calculated_priority на основі залишку часу до дедлайну
        та повертає ефективний пріоритет effective_priority.
        """
        self.ensure_active("перерахувати пріоритет деактивованої задачі")

        ref_now = now or datetime.now(UTC)
        new_priority = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=self.due_datetime,
            created_at_utc=self.created_at,
            reference_time_utc=ref_now,
            base_priority=self.base_priority,
            auto_escalate=auto_escalate,
        )
        self.calculated_priority = new_priority
        self.mark_updated()
        return self.effective_priority
