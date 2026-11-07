from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.domain.enums import UserRole
from src.modules.users.domain.exceptions import (
    SuperAdminDeletionForbiddenError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository


class SoftDeleteUserUseCase:
    """Use Case м'якої деактивації облікового запису користувача (Soft Delete)."""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(self, user_id: UUID, *, commit: bool = True) -> None:
        """Позначає користувача як видаленого з перевіркою системної ролі."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        # Викликає доменний метод, який захищає SUPER_ADMIN та встановлює deleted_at
        user.soft_delete()
        await self._user_repo.save(user)

        if commit:
            await self._uow.commit()


class HardDeleteUserUseCase:
    """Use Case фізичного видалення облікового запису користувача (Hard Delete)."""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(self, user_id: UUID, *, commit: bool = True) -> None:
        """Остаточно видаляє запис користувача з бази даних."""
        user = await self._user_repo.get_by_id(user_id, include_deleted=True)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        if user.role == UserRole.SUPER_ADMIN:
            raise SuperAdminDeletionForbiddenError("Обліковий запис SuperAdmin не може бути видалений.")

        await self._user_repo.delete_by_id(user_id)

        if commit:
            await self._uow.commit()
