from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from src.core.exceptions import ForbiddenException, NotFoundException
from src.core.protocols import IUnitOfWork
from src.modules.reminders.application.dto import UpdateReminderCommand
from src.modules.reminders.domain.aggregates import (
    DeadlineTaskReminder,
    MedicationReminder,
    OpenTaskReminder,
    SubscriptionReminder,
)
from src.modules.reminders.domain.exceptions import ReminderNotFoundError
from src.modules.reminders.domain.interfaces import IReminderRepository
from src.modules.reminders.domain.services.schedule_calculator import ScheduleCalculator
from src.modules.reminders.domain.value_objects import (
    LeadTimes,
    Money,
    QuietHoursWindow,
    parse_schedule_config,
)
from src.modules.users.public import UsersPublicGateway
from src.utils import check_version


class UpdateReminderUseCase:
    """Сценарій повного перезапису нагадування (HTTP PUT Full Update)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        reminder_repo: IReminderRepository,
        users_gateway: UsersPublicGateway,
    ) -> None:
        self._uow = uow
        self._reminder_repo = reminder_repo
        self._users_gateway = users_gateway

    async def execute(
        self,
        reminder_id: UUID,
        user_id: UUID,
        cmd: UpdateReminderCommand,
    ) -> None:
        """Повне оновлення нагадування з перевіркою версії (OCC) та повного набору полів."""
        reminder = await self._reminder_repo.get_by_id(reminder_id)
        if reminder is None:
            raise ReminderNotFoundError("Нагадування не знайдено.")

        if reminder.user_id != user_id:
            raise ForbiddenException("Немає прав для редагування цього нагадування.")

        reminder.ensure_active("редагувати деактивоване нагадування")
        check_version(reminder.version, cmd.version, entity_title="нагадування")

        ScheduleCalculator.validate_compatibility(reminder.reminder_type, cmd.schedule_logic)
        parsed_config = parse_schedule_config(cmd.schedule_logic, cmd.schedule_config)

        user_ctx = await self._users_gateway.get_notification_context(user_id)
        if user_ctx is None:
            raise NotFoundException("Профіль користувача не знайдено.")

        quiet_hours = QuietHoursWindow(
            start_time=user_ctx.quiet_hours_start,
            end_time=user_ctx.quiet_hours_end,
            timezone_name=user_ctx.timezone,
        )

        now_utc = datetime.now(UTC)
        lead_times = LeadTimes(cmd.lead_times)

        next_trigger = ScheduleCalculator.calculate_next_trigger(
            reminder_type=reminder.reminder_type,
            schedule_logic=cmd.schedule_logic,
            schedule_config=parsed_config,
            reference_time_utc=now_utc,
            lead_times=lead_times,
            user_timezone=user_ctx.timezone,
            quiet_hours=quiet_hours,
            strict_schedule=cmd.strict_schedule,
            is_trial=cmd.is_trial,
            trial_end_date=cmd.trial_end_date,
        )

        reminder.schedule_logic = cmd.schedule_logic
        reminder.title = cmd.title
        reminder.description = cmd.description
        reminder.schedule_config = parsed_config
        reminder.lead_times = lead_times
        reminder.status = cmd.status
        reminder.next_trigger_at = next_trigger

        if isinstance(reminder, OpenTaskReminder):
            reminder.base_priority = cmd.base_priority
        elif isinstance(reminder, DeadlineTaskReminder):
            if cmd.due_datetime is not None:
                reminder.due_datetime = cmd.due_datetime
            reminder.base_priority = cmd.base_priority
            reminder.recalculate_priority(now_utc, auto_escalate=user_ctx.auto_deadline_priority_escalation)
        elif isinstance(reminder, SubscriptionReminder):
            curr = cmd.currency or reminder.regular_amount.currency
            reminder.regular_amount = Money(amount=cmd.regular_amount or Decimal("0.00"), currency=curr)
            reminder.is_trial = cmd.is_trial
            reminder.trial_end_date = cmd.trial_end_date
            reminder.discount_amount = (
                Money(amount=cmd.discount_amount, currency=curr) if cmd.discount_amount is not None else None
            )
            reminder.discount_cycles_total = cmd.discount_cycles_total
            reminder.discount_cycles_remaining = cmd.discount_cycles_remaining
        elif isinstance(reminder, MedicationReminder):
            reminder.course_duration_days = cmd.course_duration_days
            reminder.medication_start_date = cmd.medication_start_date
            reminder.medication_end_date = cmd.medication_end_date
            reminder.strict_schedule = cmd.strict_schedule

        reminder.mark_updated()
        await self._reminder_repo.save(reminder)
        await self._uow.commit()
