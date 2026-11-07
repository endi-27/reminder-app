from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from uuid6 import uuid7

from src.core.exceptions import NotFoundException
from src.core.protocols import IUnitOfWork
from src.modules.reminders.application.dto import CreateReminderCommand
from src.modules.reminders.domain.aggregates import (
    AnniversaryReminder,
    DeadlineTaskReminder,
    MedicationReminder,
    OpenTaskReminder,
    ReminderAggregate,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import ReminderType
from src.modules.reminders.domain.interfaces import IReminderRepository
from src.modules.reminders.domain.services.schedule_calculator import ScheduleCalculator
from src.modules.reminders.domain.value_objects import (
    ExactDateDeadlineConfig,
    ExactDateTimeDeadlineConfig,
    LeadTimes,
    Money,
    QuietHoursWindow,
    parse_schedule_config,
)
from src.modules.users.public import UsersPublicGateway


class CreateReminderUseCase:
    """Сценарій створення нового нагадування з валідацією сумісності та розрахунком розкладу."""

    def __init__(
        self,
        uow: IUnitOfWork,
        reminder_repo: IReminderRepository,
        users_gateway: UsersPublicGateway,
    ) -> None:
        self._uow = uow
        self._reminder_repo = reminder_repo
        self._users_gateway = users_gateway

    async def execute(self, user_id: UUID, cmd: CreateReminderCommand) -> ReminderAggregate:
        """
        Виконує створення нагадування:
        1. Валідує сумісність пари (reminder_type, schedule_logic).
        2. Парсить та валідує schedule_config.
        3. Завантажує контекст сповіщень користувача (таймзона, тихі години, авто-ескалація).
        4. Розраховує перший момент спрацювання next_trigger_at.
        5. Інстанціює чистий доменний агрегат із 5 доступних та зберігає в БД.
        """
        ScheduleCalculator.validate_compatibility(cmd.reminder_type, cmd.schedule_logic)
        parsed_config = parse_schedule_config(cmd.schedule_logic, cmd.schedule_config)

        user_ctx = await self._users_gateway.get_notification_context(user_id)
        if user_ctx is None:
            raise NotFoundException("Профіль або налаштування користувача не знайдено.")

        user_tz = user_ctx.timezone
        quiet_hours = QuietHoursWindow(
            start_time=user_ctx.quiet_hours_start,
            end_time=user_ctx.quiet_hours_end,
            timezone_name=user_tz,
        )

        now_utc = datetime.now(UTC)
        lead_times = LeadTimes(cmd.lead_times)

        next_trigger = ScheduleCalculator.calculate_next_trigger(
            reminder_type=cmd.reminder_type,
            schedule_logic=cmd.schedule_logic,
            schedule_config=parsed_config,
            reference_time_utc=now_utc,
            lead_times=lead_times,
            user_timezone=user_tz,
            quiet_hours=quiet_hours,
            strict_schedule=cmd.strict_schedule,
            is_trial=cmd.is_trial,
            trial_end_date=cmd.trial_end_date,
        )

        reminder_id = uuid7()
        reminder: ReminderAggregate
        if cmd.reminder_type == ReminderType.ANNIVERSARY:
            reminder = AnniversaryReminder(
                id=reminder_id,
                user_id=user_id,
                reminder_type=cmd.reminder_type,
                schedule_logic=cmd.schedule_logic,
                title=cmd.title,
                description=cmd.description,
                next_trigger_at=next_trigger,
                schedule_config=parsed_config,
                lead_times=lead_times,
            )

        elif cmd.reminder_type == ReminderType.OPEN_TASK:
            reminder = OpenTaskReminder(
                id=reminder_id,
                user_id=user_id,
                reminder_type=cmd.reminder_type,
                schedule_logic=cmd.schedule_logic,
                title=cmd.title,
                description=cmd.description,
                next_trigger_at=next_trigger,
                schedule_config=parsed_config,
                lead_times=lead_times,
                base_priority=cmd.base_priority,
            )

        elif cmd.reminder_type == ReminderType.DEADLINE_TASK:
            due_dt = cmd.due_datetime
            if due_dt is None:
                if isinstance(parsed_config, ExactDateTimeDeadlineConfig):
                    due_dt = parsed_config.due_datetime
                elif isinstance(parsed_config, ExactDateDeadlineConfig):
                    loc_dt = datetime.combine(
                        parsed_config.due_date,
                        parsed_config.default_notify_time,
                        tzinfo=ZoneInfo(user_tz),
                    )
                    due_dt = loc_dt.astimezone(UTC)
                else:
                    due_dt = next_trigger

            due_dt = due_dt.replace(tzinfo=UTC) if due_dt.tzinfo is None else due_dt.astimezone(UTC)

            calc_priority = ScheduleCalculator.calculate_dynamic_priority(
                due_datetime_utc=due_dt,
                created_at_utc=now_utc,
                reference_time_utc=now_utc,
                base_priority=cmd.base_priority,
                auto_escalate=user_ctx.auto_deadline_priority_escalation,
            )
            reminder = DeadlineTaskReminder(
                id=reminder_id,
                user_id=user_id,
                reminder_type=cmd.reminder_type,
                schedule_logic=cmd.schedule_logic,
                title=cmd.title,
                description=cmd.description,
                next_trigger_at=next_trigger,
                schedule_config=parsed_config,
                lead_times=lead_times,
                due_datetime=due_dt,
                base_priority=cmd.base_priority,
                calculated_priority=calc_priority,
            )

        elif cmd.reminder_type == ReminderType.SUBSCRIPTION:
            reg_money = Money(amount=cmd.regular_amount or Decimal("0.00"), currency=cmd.currency)
            disc_money = (
                Money(amount=cmd.discount_amount, currency=cmd.currency) if cmd.discount_amount is not None else None
            )
            reminder = SubscriptionReminder(
                id=reminder_id,
                user_id=user_id,
                reminder_type=cmd.reminder_type,
                schedule_logic=cmd.schedule_logic,
                title=cmd.title,
                description=cmd.description,
                next_trigger_at=next_trigger,
                schedule_config=parsed_config,
                lead_times=lead_times,
                regular_amount=reg_money,
                is_trial=cmd.is_trial,
                trial_end_date=cmd.trial_end_date,
                discount_amount=disc_money,
                discount_cycles_total=cmd.discount_cycles_total,
                discount_cycles_remaining=cmd.discount_cycles_remaining,
            )

        elif cmd.reminder_type == ReminderType.MEDICATION:
            reminder = MedicationReminder(
                id=reminder_id,
                user_id=user_id,
                reminder_type=cmd.reminder_type,
                schedule_logic=cmd.schedule_logic,
                title=cmd.title,
                description=cmd.description,
                next_trigger_at=next_trigger,
                schedule_config=parsed_config,
                lead_times=lead_times,
                course_duration_days=cmd.course_duration_days,
                medication_start_date=cmd.medication_start_date,
                medication_end_date=cmd.medication_end_date,
                strict_schedule=cmd.strict_schedule,
            )

        else:
            raise ValueError(f"Непідтримуваний тип нагадування: {cmd.reminder_type}")

        await self._reminder_repo.save(reminder)
        await self._uow.commit()
        return reminder
