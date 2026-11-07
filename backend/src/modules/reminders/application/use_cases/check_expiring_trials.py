from datetime import UTC, datetime

from src.core.protocols import INotificationPublisher, IUnitOfWork
from src.infrastructure.notifications.dto import NotificationEventType, NotificationPayload
from src.modules.reminders.domain.interfaces import IReminderRepository
from src.modules.users.public import UsersPublicGateway


class CheckExpiringTrialsAndDiscountsUseCase:
    """Сценарій щоденного моніторингу підписок із закінченням пробного періоду або знижки."""

    def __init__(
        self,
        uow: IUnitOfWork,
        reminder_repo: IReminderRepository,
        users_gateway: UsersPublicGateway,
        publisher: INotificationPublisher,
    ) -> None:
        self._uow = uow
        self._reminder_repo = reminder_repo
        self._users_gateway = users_gateway
        self._publisher = publisher

    async def execute(self, now: datetime | None = None, limit: int = 100, commit: bool = True) -> int:
        """Перевіряє активні підписки у статусі TRIAL або з залишковими циклами знижки."""
        now_utc = now or datetime.now(UTC)
        now_utc = now_utc.replace(tzinfo=UTC) if now_utc.tzinfo is None else now_utc.astimezone(UTC)

        subscriptions = await self._reminder_repo.fetch_expiring_trials_and_discounts(now_utc, limit=limit)
        if not subscriptions:
            return 0

        user_ids = list({s.user_id for s in subscriptions})
        user_contexts = await self._users_gateway.get_notification_contexts_by_ids(user_ids)
        payloads: list[NotificationPayload] = []

        for sub in subscriptions:
            ctx = user_contexts.get(sub.user_id)
            if ctx is None or ctx.telegram_chat_id is None:
                continue

            # Якщо пробний період завершився
            if sub.is_trial and sub.trial_end_date and sub.trial_end_date <= now_utc.date():
                sub.convert_trial_to_paid(now_utc, user_timezone=ctx.timezone)
                await self._reminder_repo.save(sub)

                payloads.append(
                    NotificationPayload(
                        event_type=NotificationEventType.TRIAL_EXPIRED,
                        recipient_channel="telegram",
                        recipient_chat_id=ctx.telegram_chat_id,
                        user_timezone=ctx.timezone,
                        reminder_id=sub.id,
                        reminder_type=sub.reminder_type,
                        title=sub.title,
                        description=sub.description,
                        amount=sub.regular_amount.amount,
                        currency=sub.regular_amount.currency,
                    )
                )

        if commit:
            await self._uow.commit()

        if payloads:
            await self._publisher.publish_many(payloads)

        return len(payloads)
