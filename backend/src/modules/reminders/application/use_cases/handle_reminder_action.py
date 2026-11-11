from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.core.exceptions import ForbiddenException, NotFoundException, ValidationException
from src.core.protocols import IUnitOfWork
from src.modules.reminders.application.dto import ReminderActionCommand, ReminderActionType
from src.modules.reminders.domain.aggregates import (
    MedicationReminder,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import MedicationLogStatus
from src.modules.reminders.domain.exceptions import ReminderNotFoundError
from src.modules.reminders.domain.interfaces import (
    IMedicationLogRepository,
    IReminderRepository,
)
from src.modules.reminders.domain.value_objects import QuietHoursWindow
from src.modules.users.public import UsersPublicGateway


class HandleReminderActionUseCase:
    """Сценарій обробки інтерактивних дій користувача над нагадуванням (RPC ендпоінт)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        reminder_repo: IReminderRepository,
        medication_log_repo: IMedicationLogRepository,
        users_gateway: UsersPublicGateway,
    ) -> None:
        self._uow = uow
        self._reminder_repo = reminder_repo
        self._medication_log_repo = medication_log_repo
        self._users_gateway = users_gateway

    async def execute(
        self,
        reminder_id: UUID,
        user_id: UUID,
        cmd: ReminderActionCommand,
    ) -> None:
        """Виконує вибрану дію над агрегатом нагадування та зберігає результати в БД."""
        reminder = await self._reminder_repo.get_by_id(reminder_id)
        if reminder is None:
            raise ReminderNotFoundError("Нагадування не знайдено.")

        if reminder.user_id != user_id:
            raise ForbiddenException("Немає прав для виконання дій над цим нагадуванням.")

        now_utc = datetime.now(UTC)

        if cmd.action == ReminderActionType.COMPLETE:
            reminder.complete()

        elif cmd.action == ReminderActionType.SNOOZE:
            reminder.snooze(timedelta(minutes=cmd.snooze_minutes), now=now_utc)

        elif cmd.action == ReminderActionType.PAUSE:
            reminder.pause()

        elif cmd.action == ReminderActionType.RESUME:
            user_ctx = await self._users_gateway.get_notification_context(user_id)
            user_tz = user_ctx.timezone if user_ctx else "Europe/Kyiv"
            quiet_hours = (
                QuietHoursWindow(
                    start_time=user_ctx.quiet_hours_start,
                    end_time=user_ctx.quiet_hours_end,
                    timezone_name=user_ctx.timezone,
                )
                if user_ctx and user_ctx.quiet_hours_start and user_ctx.quiet_hours_end
                else None
            )
            reminder.resume(reference_time=now_utc, user_timezone=user_tz, quiet_hours=quiet_hours)

        elif cmd.action == ReminderActionType.CANCEL:
            reminder.cancel()

        elif cmd.action == ReminderActionType.RECORD_PAYMENT:
            if not isinstance(reminder, SubscriptionReminder):
                raise ValidationException("Дія RECORD_PAYMENT застосовна виключно до підписок.")
            user_ctx = await self._users_gateway.get_notification_context(user_id)
            user_tz = user_ctx.timezone if user_ctx else "Europe/Kyiv"
            reminder.record_payment(reference_time=now_utc, user_timezone=user_tz)

        elif cmd.action == ReminderActionType.RECORD_MEDICATION_INTAKE:
            if not isinstance(reminder, MedicationReminder):
                raise ValidationException("Дія RECORD_MEDICATION_INTAKE застосовна виключно до ліків.")

            user_ctx = await self._users_gateway.get_notification_context(user_id)
            if user_ctx is None:
                raise NotFoundException("Профіль користувача не знайдено.")

            quiet_hours = QuietHoursWindow(
                start_time=user_ctx.quiet_hours_start,
                end_time=user_ctx.quiet_hours_end,
                timezone_name=user_ctx.timezone,
            )
            med_status = cmd.medication_status or MedicationLogStatus.TAKEN
            log = reminder.record_intake(
                status=med_status,
                scheduled_at=cmd.scheduled_at,
                recorded_at=now_utc,
                user_timezone=user_ctx.timezone,
                quiet_hours=quiet_hours,
            )
            await self._medication_log_repo.save(log)

        else:
            raise ValidationException(f"Невідома дія над нагадуванням: {cmd.action}")

        await self._reminder_repo.save(reminder)
        await self._uow.commit()
