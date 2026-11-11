from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import or_, select, update

from src.infrastructure.db.repositories import SqlAlchemyBaseCrudRepository
from src.modules.reminders.domain.aggregates import (
    OpenTaskReminder,
    ReminderAggregate,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import ReminderStatus, ReminderType
from src.modules.reminders.domain.interfaces import IReminderRepository
from src.modules.reminders.infrastructure.mappers import ReminderMapper
from src.modules.reminders.infrastructure.models import ReminderModel


class SqlAlchemyReminderRepository(
    SqlAlchemyBaseCrudRepository[ReminderAggregate, ReminderModel],
    IReminderRepository,
):
    """
    Репозиторій для роботи з єдиною таблицею reminders (Single Table Inheritance).

    Реалізує високоефективні вибірки для шедулера з оптимістичним блокуванням
    рядків FOR UPDATE SKIP LOCKED.
    """

    _model_cls = ReminderModel
    _mapper = ReminderMapper

    async def fetch_due_for_scheduler(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[ReminderAggregate]:
        """
        Вибірка чергових активних нагадувань для щохвилинного Cron-полера ARQ
        за індексом idx_reminders_scheduler із блокуванням SKIP LOCKED.
        """
        stmt = (
            select(ReminderModel)
            .where(
                ReminderModel.next_trigger_at <= now_utc,
                ReminderModel.status.in_((ReminderStatus.ACTIVE, ReminderStatus.TRIAL)),
                ReminderModel.deleted_at.is_(None),
            )
            .order_by(ReminderModel.next_trigger_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def fetch_active_open_tasks_for_digest(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[OpenTaskReminder]:
        """Отримує активні відкриті справи (OPEN_TASK) для формування щоденних дайджестів."""
        stmt = (
            select(ReminderModel)
            .where(
                ReminderModel.reminder_type == ReminderType.OPEN_TASK,
                ReminderModel.status == ReminderStatus.ACTIVE,
                ReminderModel.deleted_at.is_(None),
                ReminderModel.next_trigger_at <= now_utc,
            )
            .order_by(ReminderModel.next_trigger_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [cast(OpenTaskReminder, self._to_domain(m)) for m in models]

    async def fetch_expiring_trials_and_discounts(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[SubscriptionReminder]:
        """Отримує підписки у статусі TRIAL або з акційною знижкою для відправки попереджень."""
        stmt = (
            select(ReminderModel)
            .where(
                ReminderModel.reminder_type == ReminderType.SUBSCRIPTION,
                ReminderModel.status.in_((ReminderStatus.TRIAL, ReminderStatus.ACTIVE)),
                ReminderModel.deleted_at.is_(None),
                or_(
                    ReminderModel.is_trial.is_(True),
                    ReminderModel.discount_cycles_remaining > 0,
                ),
            )
            .order_by(ReminderModel.next_trigger_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [cast(SubscriptionReminder, self._to_domain(m)) for m in models]

    async def pause_active_deadline_tasks_by_user_id(self, user_id: UUID) -> int:
        """Переводить усі активні задачі з дедлайном у статус PAUSED для вказаного користувача."""
        stmt = (
            update(ReminderModel)
            .where(
                ReminderModel.user_id == user_id,
                ReminderModel.reminder_type == ReminderType.DEADLINE_TASK,
                ReminderModel.status == ReminderStatus.ACTIVE,
                ReminderModel.deleted_at.is_(None),
            )
            .values(
                status=ReminderStatus.PAUSED,
                updated_at=datetime.now(UTC),
                version=ReminderModel.version + 1,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)

    async def pause_all_active_reminders_by_user_id(self, user_id: UUID) -> int:
        """Переводить усі активні та тріальні нагадування будь-якого типу у статус PAUSED для вказаного користувача."""
        stmt = (
            update(ReminderModel)
            .where(
                ReminderModel.user_id == user_id,
                ReminderModel.status.in_([ReminderStatus.ACTIVE, ReminderStatus.TRIAL]),
                ReminderModel.deleted_at.is_(None),
            )
            .values(
                status=ReminderStatus.PAUSED,
                updated_at=datetime.now(UTC),
                version=ReminderModel.version + 1,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)
