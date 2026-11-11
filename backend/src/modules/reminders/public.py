from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.protocols import INotificationPublisher, IUnitOfWork
from src.core.redis import RedisClient
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications.redis_queue_publisher import RedisQueuePublisher
from src.modules.finance.public import FinancePublicGateway
from src.modules.reminders.application.dto import SchedulerBatchResultDTO
from src.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from src.modules.reminders.queries.dto import ReminderResponseDTO
from src.modules.reminders.queries.query_service import ReminderQueryService
from src.modules.users.public import UsersPublicGateway


class RemindersPublicGateway:
    """
    Публічний фасад модуля нагадувань для фонових воркерів та міжмодульної взаємодії (Інваріант 1).

    Забезпечує безпечний запуск щохвилинного шедулера ARQ, щоденних дайджестів
    та перевірки термінів підписок.
    """

    def __init__(
        self,
        session: AsyncSession,
        uow: IUnitOfWork | None = None,
        redis_client: RedisClient | None = None,
        publisher: INotificationPublisher | None = None,
        users_gateway: UsersPublicGateway | None = None,
        finance_gateway: FinancePublicGateway | None = None,
    ) -> None:
        self._session = session
        self._external_uow = uow
        self._uow = uow or SqlAlchemyUnitOfWork(session=session)
        self._reminder_repo = SqlAlchemyReminderRepository(session=session)
        self._query_service = ReminderQueryService(session=session)

        # Ініціалізація залежностей
        self._users_gateway = users_gateway or UsersPublicGateway(session=session, uow=self._uow)
        self._finance_gateway = finance_gateway or FinancePublicGateway(session=session, uow=self._uow)

        if publisher is not None:
            self._publisher = publisher
        elif redis_client is not None:
            self._publisher = RedisQueuePublisher(redis_client=redis_client)
        else:
            self._publisher = RedisQueuePublisher(redis_client=RedisClient())

    async def get_reminder_by_id(
        self,
        reminder_id: UUID,
        user_id: UUID | None = None,
    ) -> ReminderResponseDTO | None:
        """Отримання даних нагадування за ID через Read-Side QueryService."""
        return await self._query_service.get_by_id(reminder_id=reminder_id, user_id=user_id)

    async def process_due_reminders(
        self,
        now: datetime | None = None,
        batch_size: int = 100,
    ) -> SchedulerBatchResultDTO:
        """
        Запуск обробки чергових нагадувань для щохвилинного Cron-полера ARQ.

        Якщо фасад викликано в рамках зовнішньої транзакції, коміт делегується ініціатору (Інваріант 7).
        """
        from src.modules.reminders.application.use_cases.process_due_reminders import (
            ProcessDueRemindersUseCase,
        )

        use_case = ProcessDueRemindersUseCase(
            uow=self._uow,
            reminder_repo=self._reminder_repo,
            users_gateway=self._users_gateway,
            finance_gateway=self._finance_gateway,
            publisher=self._publisher,
        )
        should_commit = self._external_uow is None
        return await use_case.execute(now=now, batch_size=batch_size, commit=should_commit)

    async def process_daily_digest(
        self,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        """Запуск розсилки щоденних дайджестів відкритих справ (OPEN_TASK)."""
        from src.modules.reminders.application.use_cases.process_daily_digest import (
            ProcessDailyDigestUseCase,
        )

        use_case = ProcessDailyDigestUseCase(
            uow=self._uow,
            reminder_repo=self._reminder_repo,
            users_gateway=self._users_gateway,
            publisher=self._publisher,
        )
        should_commit = self._external_uow is None
        return await use_case.execute(now=now, limit=limit, commit=should_commit)

    async def check_expiring_trials_and_discounts(
        self,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        """Запуск щоденного моніторингу закінчення пробних періодів і знижок підписок."""
        from src.modules.reminders.application.use_cases.check_expiring_trials import (
            CheckExpiringTrialsAndDiscountsUseCase,
        )

        use_case = CheckExpiringTrialsAndDiscountsUseCase(
            uow=self._uow,
            reminder_repo=self._reminder_repo,
            users_gateway=self._users_gateway,
            publisher=self._publisher,
        )
        should_commit = self._external_uow is None
        return await use_case.execute(now=now, limit=limit, commit=should_commit)

    async def pause_deadline_tasks_by_user_id(
        self,
        user_id: UUID,
        *,
        uow: IUnitOfWork | None = None,
    ) -> int:
        """
        Призупиняє всі активні задачі з дедлайном вказаного користувача.
        Ніколи не робить commit самостійно, якщо передано зовнішній uow (Інваріант 7).
        """
        count = await self._reminder_repo.pause_active_deadline_tasks_by_user_id(user_id)
        if uow is None and self._external_uow is None:
            await self._uow.commit()
        return count

    async def pause_all_active_reminders_by_user_id(
        self,
        user_id: UUID,
        *,
        uow: IUnitOfWork | None = None,
    ) -> int:
        """
        Призупиняє всі активні та тріальні нагадування будь-якого типу вказаного користувача (при блокуванні).
        Ніколи не робить commit самостійно, якщо передано зовнішній uow (Інваріант 7).
        """
        count = await self._reminder_repo.pause_all_active_reminders_by_user_id(user_id)
        if uow is None and self._external_uow is None:
            await self._uow.commit()
        return count


__all__ = [
    "RemindersPublicGateway",
]
