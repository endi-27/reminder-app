from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from src.core.protocols import INotificationPublisher, IUnitOfWork
from src.infrastructure.notifications.dto import NotificationPayload
from src.modules.reminders.domain.aggregates import OpenTaskReminder
from src.modules.reminders.domain.interfaces import IReminderRepository
from src.modules.reminders.domain.value_objects import QuietHoursWindow
from src.modules.users.public import UsersPublicGateway


class ProcessDailyDigestUseCase:
    """Сценарій формування та розсилки щоденних дайджестів відкритих справ (OPEN_TASK)."""

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
        """Збирає чергові відкриті справи користувачів, формує зведені дайджести та надсилає їх."""
        now_utc = now or datetime.now(UTC)
        now_utc = now_utc.replace(tzinfo=UTC) if now_utc.tzinfo is None else now_utc.astimezone(UTC)

        tasks = await self._reminder_repo.fetch_active_open_tasks_for_digest(now_utc, limit=limit)
        if not tasks:
            return 0

        grouped_by_user: dict[UUID, list[OpenTaskReminder]] = defaultdict(list)
        for task in tasks:
            grouped_by_user[task.user_id].append(task)

        user_contexts = await self._users_gateway.get_notification_contexts_by_ids(list(grouped_by_user.keys()))
        payloads: list[NotificationPayload] = []

        for user_id, user_tasks in grouped_by_user.items():
            ctx = user_contexts.get(user_id)
            if ctx is None or ctx.telegram_chat_id is None:
                continue

            quiet_hours = QuietHoursWindow(
                start_time=ctx.quiet_hours_start,
                end_time=ctx.quiet_hours_end,
                timezone_name=ctx.timezone,
            )

            lines = [f"• {t.title}" for t in user_tasks]
            body = "📋 Ваш щоденний дайджест відкритих справ:\n" + "\n".join(lines)

            payloads.append(
                NotificationPayload(
                    recipient_channel="telegram",
                    recipient_chat_id=ctx.telegram_chat_id,
                    title="Щоденний дайджест справ",
                    body=body,
                )
            )

            for task in user_tasks:
                task.advance_schedule(now_utc, user_timezone=ctx.timezone, quiet_hours=quiet_hours)
                await self._reminder_repo.save(task)

        if commit:
            await self._uow.commit()

        if payloads:
            await self._publisher.publish_many(payloads)

        return len(payloads)
