from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.core.domain.enums import CurrencyCode
from src.core.protocols import INotificationPublisher, IUnitOfWork
from src.infrastructure.notifications.dto import NotificationEventType, NotificationPayload
from src.modules.finance.public import FinancePublicGateway
from src.modules.reminders.application.dto import SchedulerBatchResultDTO
from src.modules.reminders.domain.aggregates import (
    AnniversaryReminder,
    DeadlineTaskReminder,
    MedicationReminder,
    OpenTaskReminder,
    SubscriptionReminder,
)
from src.modules.reminders.domain.interfaces import IReminderRepository
from src.modules.reminders.domain.value_objects import QuietHoursWindow
from src.modules.users.public import UsersPublicGateway


class ProcessDueRemindersUseCase:
    """
    Головний Use Case щохвилинного Cron-полера шедулера ARQ.

    Вибирає нагадування, час спрацювання яких настав, перевіряє вікно тихих годин,
    збагачує фінансовими курсами та пріоритетами, формує сповіщення у чергу Redis
    та просуває розклад вперед за принципом Time-Series Projection.
    """

    def __init__(
        self,
        uow: IUnitOfWork,
        reminder_repo: IReminderRepository,
        users_gateway: UsersPublicGateway,
        finance_gateway: FinancePublicGateway,
        publisher: INotificationPublisher,
    ) -> None:
        self._uow = uow
        self._reminder_repo = reminder_repo
        self._users_gateway = users_gateway
        self._finance_gateway = finance_gateway
        self._publisher = publisher

    async def execute(
        self,
        now: datetime | None = None,
        batch_size: int = 100,
        commit: bool = True,
    ) -> SchedulerBatchResultDTO:
        """Обробка пачки нагадувань, готових до відправки на момент часу now."""
        now_utc = now or datetime.now(UTC)
        now_utc = now_utc.replace(tzinfo=UTC) if now_utc.tzinfo is None else now_utc.astimezone(UTC)

        reminders = await self._reminder_repo.fetch_due_for_scheduler(now_utc, limit=batch_size)
        if not reminders:
            return SchedulerBatchResultDTO(
                processed_count=0,
                notifications_queued=0,
                deferred_to_quiet_hours=0,
                completed_or_converted=0,
            )

        user_ids = list({r.user_id for r in reminders})
        user_contexts = await self._users_gateway.get_notification_contexts_by_ids(user_ids)

        processed_count = 0
        notifications_queued = 0
        deferred_to_quiet_hours = 0
        completed_or_converted = 0
        payloads_to_publish: list[NotificationPayload] = []

        for reminder in reminders:
            processed_count += 1
            ctx = user_contexts.get(reminder.user_id)
            if ctx is None:
                continue

            quiet_hours = QuietHoursWindow(
                start_time=ctx.quiet_hours_start,
                end_time=ctx.quiet_hours_end,
                timezone_name=ctx.timezone,
            )

            is_strict = getattr(reminder, "strict_schedule", False)
            disable_sound = quiet_hours.should_disable_sound(now_utc, strict_schedule=is_strict)

            if isinstance(reminder, SubscriptionReminder):
                active_money = reminder.active_amount
                conv_amount_uah: Decimal | None = None
                rate_provider: str | None = None
                is_stale: bool = False
                if active_money.currency in (CurrencyCode.USD, CurrencyCode.EUR):
                    conv = await self._finance_gateway.convert_to_uah(
                        amount=active_money.amount,
                        currency=active_money.currency.value,
                        preferred_bank=ctx.preferred_bank.value,
                    )
                    conv_amount_uah = conv.amount_uah
                    rate_provider = str(conv.provider_used)
                    is_stale = conv.is_stale_fallback

                if ctx.is_active and ctx.telegram_chat_id is not None:
                    payloads_to_publish.append(
                        NotificationPayload(
                            event_type=NotificationEventType.REMINDER_DUE,
                            recipient_channel="telegram",
                            recipient_chat_id=ctx.telegram_chat_id,
                            user_timezone=ctx.timezone,
                            disable_sound=disable_sound,
                            reminder_id=reminder.id,
                            reminder_type=reminder.reminder_type,
                            title=reminder.title,
                            description=reminder.description,
                            amount=active_money.amount,
                            currency=active_money.currency,
                            converted_amount_uah=conv_amount_uah,
                            rate_provider=rate_provider,
                            is_stale_rate_fallback=is_stale,
                            is_trial=reminder.is_trial,
                            is_last_discount_cycle=reminder.is_last_discount_cycle,
                        )
                    )
                    notifications_queued += 1

            elif isinstance(reminder, MedicationReminder) and ctx.is_active and ctx.telegram_chat_id is not None:
                payloads_to_publish.append(
                    NotificationPayload(
                        event_type=NotificationEventType.REMINDER_DUE,
                        recipient_channel="telegram",
                        recipient_chat_id=ctx.telegram_chat_id,
                        user_timezone=ctx.timezone,
                        disable_sound=disable_sound,
                        reminder_id=reminder.id,
                        reminder_type=reminder.reminder_type,
                        title=reminder.title,
                        description=reminder.description,
                        medication_end_date=reminder.medication_end_date,
                        strict_schedule=reminder.strict_schedule,
                    )
                )
                notifications_queued += 1

            elif isinstance(reminder, DeadlineTaskReminder):
                effective_prio = reminder.recalculate_priority(
                    now_utc,
                    auto_escalate=ctx.auto_deadline_priority_escalation,
                )
                if ctx.is_active and ctx.telegram_chat_id is not None:
                    payloads_to_publish.append(
                        NotificationPayload(
                            event_type=NotificationEventType.REMINDER_DUE,
                            recipient_channel="telegram",
                            recipient_chat_id=ctx.telegram_chat_id,
                            user_timezone=ctx.timezone,
                            disable_sound=disable_sound,
                            reminder_id=reminder.id,
                            reminder_type=reminder.reminder_type,
                            title=reminder.title,
                            description=reminder.description,
                            due_datetime=reminder.due_datetime,
                            effective_priority=effective_prio,
                        )
                    )
                    notifications_queued += 1

            elif isinstance(reminder, AnniversaryReminder):
                local_now = now_utc.astimezone(ZoneInfo(ctx.timezone))
                age = reminder.calculate_age(local_now.year)
                if ctx.is_active and ctx.telegram_chat_id is not None:
                    payloads_to_publish.append(
                        NotificationPayload(
                            event_type=NotificationEventType.REMINDER_DUE,
                            recipient_channel="telegram",
                            recipient_chat_id=ctx.telegram_chat_id,
                            user_timezone=ctx.timezone,
                            disable_sound=disable_sound,
                            reminder_id=reminder.id,
                            reminder_type=reminder.reminder_type,
                            title=reminder.title,
                            description=reminder.description,
                            calculated_age=age,
                        )
                    )
                    notifications_queued += 1

            elif isinstance(reminder, OpenTaskReminder) and ctx.is_active and ctx.telegram_chat_id is not None:
                payloads_to_publish.append(
                    NotificationPayload(
                        event_type=NotificationEventType.REMINDER_DUE,
                        recipient_channel="telegram",
                        recipient_chat_id=ctx.telegram_chat_id,
                        user_timezone=ctx.timezone,
                        disable_sound=disable_sound,
                        reminder_id=reminder.id,
                        reminder_type=reminder.reminder_type,
                        title=reminder.title,
                        description=reminder.description,
                        effective_priority=reminder.base_priority,
                    )
                )
                notifications_queued += 1

            # Просування розкладу нагадування вперед
            if isinstance(reminder, MedicationReminder) and reminder.medication_end_date is not None:
                next_dt = reminder.advance_schedule(now_utc, user_timezone=ctx.timezone, quiet_hours=quiet_hours)
                end_dt_local = datetime.combine(
                    reminder.medication_end_date,
                    datetime.max.time(),
                    tzinfo=ZoneInfo(ctx.timezone),
                )
                if next_dt > end_dt_local.astimezone(UTC):
                    reminder.complete()
                    completed_or_converted += 1
            else:
                reminder.advance_schedule(now_utc, user_timezone=ctx.timezone, quiet_hours=quiet_hours)

            await self._reminder_repo.save(reminder)

        # Фіксуємо оновлення розкладів у базі перед публікацією сповіщень
        if commit:
            await self._uow.commit()

        if payloads_to_publish:
            await self._publisher.publish_many(payloads_to_publish)

        return SchedulerBatchResultDTO(
            processed_count=processed_count,
            notifications_queued=notifications_queued,
            deferred_to_quiet_hours=deferred_to_quiet_hours,
            completed_or_converted=completed_or_converted,
        )
