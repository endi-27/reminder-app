from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.core.protocols import INotificationPublisher, IUnitOfWork
from src.infrastructure.notifications.dto import ActionButton, NotificationPayload
from src.modules.finance.public import FinancePublicGateway
from src.modules.reminders.application.dto import SchedulerBatchResultDTO
from src.modules.reminders.domain.aggregates import (
    AnniversaryReminder,
    DeadlineTaskReminder,
    MedicationReminder,
    OpenTaskReminder,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import CurrencyCode, Priority
from src.modules.reminders.domain.interfaces import IReminderRepository
from src.modules.reminders.domain.value_objects import QuietHoursWindow
from src.modules.users.public import UsersPublicGateway

_PRIORITY_LABELS: dict[Priority, str] = {
    Priority.LOW: "[НИЗЬКИЙ]",
    Priority.MEDIUM: "[СЕРЕДНІЙ]",
    Priority.HIGH: "[ВИСОКИЙ]",
    Priority.CRITICAL: "[КРИТИЧНО]",
}


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
            if quiet_hours.is_in_quiet_hours(now_utc) and not is_strict:
                reminder.next_trigger_at = quiet_hours.adjust_trigger_time(now_utc, strict_schedule=False)
                reminder.mark_updated()
                await self._reminder_repo.save(reminder)
                deferred_to_quiet_hours += 1
                continue

            # Формування тексту та кнопок залежно від типу нагадування
            buttons: list[ActionButton] = []
            body: str = ""

            if isinstance(reminder, SubscriptionReminder):
                active_money = reminder.active_amount
                if active_money.currency in (CurrencyCode.USD, CurrencyCode.EUR):
                    conv = await self._finance_gateway.convert_to_uah(
                        amount=active_money.amount,
                        currency=active_money.currency.value,
                        preferred_bank=ctx.preferred_bank.value,
                    )
                    cost_text = f"{active_money} (≈ {conv.amount_uah:.2f} грн за курсом {conv.provider_used})"
                    if conv.is_stale_fallback:
                        cost_text += " ⚠️ Курс застарілий, використано офіційний курс НБУ."
                else:
                    cost_text = f"{active_money}"

                extra_warn = ""
                if reminder.is_trial:
                    extra_warn = "\n⚠️ Закінчується пробний період підписки!"
                elif reminder.is_last_discount_cycle:
                    extra_warn = "\n⚠️ Це останній платіжний цикл за зниженою акційною ціною!"

                body = f"💳 Нагадування про оплату підписки: {reminder.title}\nСума до сплати: {cost_text}{extra_warn}"
                buttons = [
                    ActionButton(text="💳 Оплачено", callback_data=f"reminder:payment:{reminder.id}"),
                    ActionButton(text="⏰ Нагадати завтра", callback_data=f"reminder:snooze:{reminder.id}:1440"),
                    ActionButton(text="❌ Скасувати підписку", callback_data=f"reminder:cancel:{reminder.id}"),
                ]

            elif isinstance(reminder, MedicationReminder):
                body = f"💊 Час прийому ліків: {reminder.title}"
                if reminder.description:
                    body += f"\n{reminder.description}"
                if reminder.medication_end_date:
                    body += f"\nКурс триває до: {reminder.medication_end_date.strftime('%d.%m.%Y')}"

                buttons = [
                    ActionButton(text="💊 Прийняв", callback_data=f"reminder:med_taken:{reminder.id}"),
                    ActionButton(text="⏰ +15 хв", callback_data=f"reminder:snooze:{reminder.id}:15"),
                    ActionButton(text="❌ Пропустив", callback_data=f"reminder:med_missed:{reminder.id}"),
                ]

            elif isinstance(reminder, DeadlineTaskReminder):
                effective_prio = reminder.recalculate_priority(
                    now_utc,
                    auto_escalate=ctx.auto_deadline_priority_escalation,
                )
                prio_badge = _PRIORITY_LABELS.get(effective_prio, "[ЗВИЧАЙНИЙ]") if effective_prio else "[ЗВИЧАЙНИЙ]"
                due_str = reminder.due_datetime.astimezone(ZoneInfo(ctx.timezone)).strftime("%d.%m.%Y %H:%M")
                body = f"{prio_badge} Дедлайн задачі: {reminder.title}\nТермін виконання: {due_str}"
                if reminder.description:
                    body += f"\n{reminder.description}"

                buttons = [
                    ActionButton(text="✅ Виконано", callback_data=f"reminder:complete:{reminder.id}"),
                    ActionButton(text="⏰ +1 год", callback_data=f"reminder:snooze:{reminder.id}:60"),
                ]

            elif isinstance(reminder, AnniversaryReminder):
                local_now = now_utc.astimezone(ZoneInfo(ctx.timezone))
                age = reminder.calculate_age(local_now.year)
                age_text = f" ({age} р.)" if age is not None else ""
                body = f"🎉 Сьогодні святкова подія: {reminder.title}{age_text}!"
                if reminder.description:
                    body += f"\n{reminder.description}"

                buttons = [
                    ActionButton(text="✅ Привітав", callback_data=f"reminder:complete:{reminder.id}"),
                ]

            elif isinstance(reminder, OpenTaskReminder):
                body = f"📋 Нагадування про справу: {reminder.title}"
                if reminder.description:
                    body += f"\n{reminder.description}"

                buttons = [
                    ActionButton(text="✅ Виконано", callback_data=f"reminder:complete:{reminder.id}"),
                    ActionButton(text="⏰ Відкласти", callback_data=f"reminder:snooze:{reminder.id}:180"),
                ]

            # Якщо у користувача підключено Telegram — ставимо сповіщення у чергу
            if ctx.telegram_chat_id is not None:
                payload = NotificationPayload(
                    recipient_channel="telegram",
                    recipient_chat_id=ctx.telegram_chat_id,
                    reminder_id=reminder.id,
                    title=reminder.title,
                    body=body,
                    buttons=buttons,
                )
                payloads_to_publish.append(payload)
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
