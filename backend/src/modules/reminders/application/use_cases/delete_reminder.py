from uuid import UUID

from src.core.exceptions import ForbiddenException
from src.core.protocols import IUnitOfWork
from src.modules.reminders.domain.exceptions import ReminderNotFoundError
from src.modules.reminders.domain.interfaces import IReminderRepository


class SoftDeleteReminderUseCase:
    """Сценарій м'якого логічного видалення нагадування (Soft Delete)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        reminder_repo: IReminderRepository,
    ) -> None:
        self._uow = uow
        self._reminder_repo = reminder_repo

    async def execute(self, reminder_id: UUID, user_id: UUID) -> None:
        """Встановлює deleted_at = NOW() для активного нагадування користувача."""
        reminder = await self._reminder_repo.get_by_id(reminder_id)
        if reminder is None:
            raise ReminderNotFoundError("Нагадування не знайдено.")

        if reminder.user_id != user_id:
            raise ForbiddenException("Немає прав для видалення цього нагадування.")

        reminder.soft_delete()
        await self._reminder_repo.save(reminder)
        await self._uow.commit()


class HardDeleteReminderUseCase:
    """Сценарій фізичного видалення нагадування з бази даних (Hard Delete)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        reminder_repo: IReminderRepository,
    ) -> None:
        self._uow = uow
        self._reminder_repo = reminder_repo

    async def execute(self, reminder_id: UUID, user_id: UUID) -> None:
        """Фізично видаляє рядок нагадування з БД з каскадним видаленням пов'язаних логів."""
        reminder = await self._reminder_repo.get_by_id(reminder_id, include_deleted=True)
        if reminder is None:
            raise ReminderNotFoundError("Нагадування не знайдено.")

        if reminder.user_id != user_id:
            raise ForbiddenException("Немає прав для остаточного видалення цього нагадування.")

        await self._reminder_repo.delete_by_id(reminder_id)
        await self._uow.commit()
