from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from src.modules.finance.application.dto import ConversionResultDTO
from src.modules.reminders.domain.aggregates import (
    MedicationIntakeLog,
    OpenTaskReminder,
    ReminderAggregate,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import ReminderStatus
from src.modules.reminders.domain.interfaces import (
    IMedicationLogRepository,
    IReminderRepository,
)
from src.modules.users.queries.dto import UserNotificationContextDTO


class InMemoryReminderRepository(IReminderRepository):
    """Швидкий тестовий дублер репозиторію нагадувань у пам'яті."""

    def __init__(self, initial_reminders: list[ReminderAggregate] | None = None) -> None:
        self.reminders: dict[UUID, ReminderAggregate] = {r.id: r for r in (initial_reminders or [])}

    async def get_by_id(
        self,
        entity_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> ReminderAggregate | None:
        r = self.reminders.get(entity_id)
        if r is None:
            return None
        if not include_deleted and not r.is_active:
            return None
        return r

    async def save(self, entity: ReminderAggregate, /) -> None:
        self.reminders[entity.id] = entity

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        if entity_id in self.reminders:
            del self.reminders[entity_id]
            return True
        return False

    async def fetch_due_for_scheduler(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[ReminderAggregate]:
        due = []
        for r in self.reminders.values():
            if not r.is_active:
                continue
            if r.status not in (ReminderStatus.ACTIVE, ReminderStatus.TRIAL):
                continue
            r_trigger = r.next_trigger_at if r.next_trigger_at.tzinfo else r.next_trigger_at.replace(tzinfo=UTC)
            ref_now = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=UTC)
            if r_trigger <= ref_now:
                due.append(r)
        due.sort(key=lambda x: x.next_trigger_at)
        return due[:limit]

    async def fetch_active_open_tasks_for_digest(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[OpenTaskReminder]:
        due = []
        for r in self.reminders.values():
            if not r.is_active or r.status != ReminderStatus.ACTIVE:
                continue
            if isinstance(r, OpenTaskReminder) and r.next_trigger_at <= now_utc:
                due.append(r)
        due.sort(key=lambda x: x.next_trigger_at)
        return due[:limit]

    async def fetch_expiring_trials_and_discounts(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[SubscriptionReminder]:
        due = []
        for r in self.reminders.values():
            if not r.is_active or r.status not in (ReminderStatus.TRIAL, ReminderStatus.ACTIVE):
                continue
            if isinstance(r, SubscriptionReminder) and (
                r.is_trial or (r.discount_cycles_remaining is not None and r.discount_cycles_remaining > 0)
            ):
                due.append(r)
        due.sort(key=lambda x: x.next_trigger_at)
        return due[:limit]


class InMemoryMedicationLogRepository(IMedicationLogRepository):
    """Швидкий тестовий дублер журналу прийому медикаментів у пам'яті."""

    def __init__(self, initial_logs: list[MedicationIntakeLog] | None = None) -> None:
        self.logs: dict[UUID, MedicationIntakeLog] = {log_item.id: log_item for log_item in (initial_logs or [])}

    async def get_by_id(
        self,
        entity_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> MedicationIntakeLog | None:
        log = self.logs.get(entity_id)
        if log is None:
            return None
        if not include_deleted and not log.is_active:
            return None
        return log

    async def save(self, entity: MedicationIntakeLog, /) -> None:
        self.logs[entity.id] = entity

    async def list_by_reminder_id(
        self,
        reminder_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> list[MedicationIntakeLog]:
        res = [
            log_item
            for log_item in self.logs.values()
            if log_item.reminder_id == reminder_id and (include_deleted or log_item.is_active)
        ]
        res.sort(key=lambda x: x.scheduled_at, reverse=True)
        return res


class FakeUsersGateway:
    """Тестовий дублер шлюзу користувачів для перевірки шедулера та Use Cases."""

    def __init__(self, contexts: dict[UUID, UserNotificationContextDTO] | None = None) -> None:
        self.contexts: dict[UUID, UserNotificationContextDTO] = contexts or {}

    async def get_notification_context(self, user_id: UUID) -> UserNotificationContextDTO | None:
        return self.contexts.get(user_id)

    async def get_notification_contexts_by_ids(
        self,
        user_ids: Sequence[UUID],
    ) -> dict[UUID, UserNotificationContextDTO]:
        return {uid: self.contexts[uid] for uid in user_ids if uid in self.contexts}


class FakeFinanceGateway:
    """Тестовий дублер фінансового шлюзу для конвертації валют."""

    def __init__(
        self,
        rate: Decimal = Decimal("41.50"),
        provider: str = "MONOBANK",
        is_stale: bool = False,
    ) -> None:
        self.rate = rate
        self.provider = provider
        self.is_stale = is_stale

    async def convert_to_uah(
        self,
        amount: Decimal,
        currency: str,
        preferred_bank: str = "MONOBANK",
    ) -> ConversionResultDTO:
        from src.modules.finance.domain.enums import (
            CurrencyCode as FinanceCurrencyCode,
        )
        from src.modules.finance.domain.enums import (
            ExchangeRateProvider,
        )

        amount_uah = (amount * self.rate).quantize(Decimal("0.01"))
        provider_val = self.provider if not self.is_stale else "NBU"
        return ConversionResultDTO(
            original_amount=amount,
            original_currency=FinanceCurrencyCode(currency),
            amount_uah=amount_uah,
            rate_used=self.rate,
            provider_used=ExchangeRateProvider(provider_val),
            is_stale_fallback=self.is_stale,
            rate_created_at=datetime.now(UTC),
        )
