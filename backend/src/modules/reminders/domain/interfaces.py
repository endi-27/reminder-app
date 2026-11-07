from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.reminders.domain.aggregates import (
    MedicationIntakeLog,
    OpenTaskReminder,
    ReminderAggregate,
    SubscriptionReminder,
)


class IReminderRepository(Protocol):
    """Порт репозиторію для персистентності агрегатів нагадувань (Single Table Inheritance)."""

    async def get_by_id(
        self,
        entity_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> ReminderAggregate | None:
        """Отримує нагадування за його первинним ключем UUIDv7."""
        ...

    async def save(self, entity: ReminderAggregate, /) -> None:
        """Зберігає або оновлює агрегат нагадування в єдиній таблиці reminders."""
        ...

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        """Виконує фізичне видалення (Hard Delete) нагадування за ідентифікатором."""
        ...

    async def fetch_due_for_scheduler(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[ReminderAggregate]:
        """
        Вибірка чергових активних нагадувань для щохвилинного Cron-полера ARQ
        за індексом next_trigger_at <= now_utc AND status IN ('ACTIVE', 'TRIAL') AND deleted_at IS NULL.
        """
        ...

    async def fetch_active_open_tasks_for_digest(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[OpenTaskReminder]:
        """Отримує активні відкриті справи (OPEN_TASK) для формування щоденних дайджестів."""
        ...

    async def fetch_expiring_trials_and_discounts(
        self,
        now_utc: datetime,
        limit: int = 100,
    ) -> list[SubscriptionReminder]:
        """Отримує підписки у статусі TRIAL або з акційною знижкою для відправки попереджень."""
        ...


class IMedicationLogRepository(Protocol):
    """Порт репозиторію для журналу прийому лікарських засобів."""

    async def get_by_id(
        self,
        entity_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> MedicationIntakeLog | None:
        """Отримує запис журналу прийому за первинним ключем UUIDv7."""
        ...

    async def save(self, entity: MedicationIntakeLog, /) -> None:
        """Зберігає або оновлює запис журналу прийому ліків."""
        ...

    async def list_by_reminder_id(
        self,
        reminder_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> list[MedicationIntakeLog]:
        """Повертає історію прийомів для зазначеного медичного нагадування."""
        ...
