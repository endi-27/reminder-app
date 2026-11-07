from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.core.domain import AggregateRoot
from src.core.exceptions import ValidationException
from src.modules.reminders.domain.enums import ReminderStatus, ReminderType, ScheduleLogicType
from src.modules.reminders.domain.exceptions import InvalidReminderStateTransitionError
from src.modules.reminders.domain.services.schedule_calculator import ScheduleCalculator
from src.modules.reminders.domain.value_objects import (
    LeadTimes,
    QuietHoursWindow,
    ScheduleConfig,
    parse_schedule_config,
)


@dataclass(kw_only=True)
class BaseReminder(AggregateRoot):
    """
    Базовий абстрактний агрегат нагадування (Rich Domain Model).
    Інкапсулює спільні атрибути, валідацію сумісності та переходи життєвого циклу.
    """

    user_id: UUID
    reminder_type: ReminderType
    schedule_logic: ScheduleLogicType
    title: str
    description: str | None = None
    status: ReminderStatus = ReminderStatus.ACTIVE
    next_trigger_at: datetime
    schedule_config: ScheduleConfig
    lead_times: LeadTimes = field(default_factory=LeadTimes)

    def __post_init__(self) -> None:
        """Валідує сумісність типу та логіки, парсить конфігурацію та нормалізує часові мітки."""
        ScheduleCalculator.validate_compatibility(self.reminder_type, self.schedule_logic)

        if not self.title or not self.title.strip():
            raise ValidationException("Заголовок нагадування не може бути порожнім.")

        self.schedule_config = parse_schedule_config(self.schedule_logic, self.schedule_config)

        if not isinstance(self.lead_times, LeadTimes):
            self.lead_times = LeadTimes(self.lead_times)

        if self.next_trigger_at.tzinfo is None:
            self.next_trigger_at = self.next_trigger_at.replace(tzinfo=UTC)
        else:
            self.next_trigger_at = self.next_trigger_at.astimezone(UTC)

    def pause(self) -> None:
        """Призупиняє активне нагадування."""
        self.ensure_active("призупинити деактивоване нагадування")
        if self.status in (ReminderStatus.COMPLETED, ReminderStatus.CANCELLED):
            raise InvalidReminderStateTransitionError("Неможливо призупинити завершене або скасоване нагадування.")
        self.status = ReminderStatus.PAUSED
        self.mark_updated()

    def resume(self) -> None:
        """Відновлює дію призупиненого нагадування."""
        self.ensure_active("відновити деактивоване нагадування")
        if self.status != ReminderStatus.PAUSED:
            raise InvalidReminderStateTransitionError("Відновити можна лише нагадування у статусі PAUSED.")
        # Якщо це підписка у тріалі — відновлюємо статус TRIAL, інакше ACTIVE
        if getattr(self, "is_trial", False):
            self.status = ReminderStatus.TRIAL
        else:
            self.status = ReminderStatus.ACTIVE
        self.mark_updated()

    def cancel(self) -> None:
        """Скасовує нагадування користувачем."""
        self.ensure_active("скасувати деактивоване нагадування")
        self.status = ReminderStatus.CANCELLED
        self.mark_updated()

    def complete(self) -> None:
        """Позначає нагадування як повністю виконане або завершене."""
        self.ensure_active("завершити деактивоване нагадування")
        self.status = ReminderStatus.COMPLETED
        self.mark_updated()

    def snooze(self, duration: timedelta, now: datetime | None = None) -> None:
        """Відкладає наступне спрацювання на вказаний інтервал часу."""
        self.ensure_active("відкласти деактивоване нагадування")
        if duration <= timedelta(0):
            raise ValidationException("Тривалість відкладення має бути додатною.")

        base_dt = now or self.next_trigger_at
        base_dt = base_dt.replace(tzinfo=UTC) if base_dt.tzinfo is None else base_dt.astimezone(UTC)

        self.next_trigger_at = base_dt + duration
        self.mark_updated()

    def advance_schedule(
        self,
        reference_time: datetime,
        user_timezone: str = "Europe/Kyiv",
        quiet_hours: QuietHoursWindow | None = None,
    ) -> datetime:
        """
        Перераховує та просуває час наступного спрацювання next_trigger_at на наступний крок розкладу.
        Повертає новий момент часу в UTC.
        """
        self.ensure_active("оновити розклад деактивованого нагадування")
        next_dt = ScheduleCalculator.calculate_next_trigger(
            reminder_type=self.reminder_type,
            schedule_logic=self.schedule_logic,
            schedule_config=self.schedule_config,
            reference_time_utc=reference_time,
            lead_times=self.lead_times,
            user_timezone=user_timezone,
            quiet_hours=quiet_hours,
            strict_schedule=getattr(self, "strict_schedule", False),
            is_trial=getattr(self, "is_trial", False),
            trial_end_date=getattr(self, "trial_end_date", None),
        )
        self.next_trigger_at = next_dt
        self.mark_updated()
        return next_dt
