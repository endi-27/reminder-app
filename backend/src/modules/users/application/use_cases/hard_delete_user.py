from uuid import UUID

from src.core.domain.enums import SystemRole
from src.core.protocols import IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.domain.exceptions import (
    SelfActionForbiddenError,
    SuperAdminActionForbiddenError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository


class HardDeleteUserUseCase:
    """Use Case остаточного фізичного видалення облікового запису користувача"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        actor: CurrentUser,
        target_user_id: UUID,
        *,
        commit: bool = True,
    ) -> None:
        """Остаточно видаляє запис користувача з бази даних разом із пов'язаними даними."""
        if actor.id == target_user_id:
            raise SelfActionForbiddenError("Заборонено видаляти власний обліковий запис.")

        user = await self._user_repo.get_by_id(target_user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {target_user_id} не знайдено.")

        if user.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminActionForbiddenError("Обліковий запис SuperAdmin не може бути видалений.")

        await self._user_repo.delete_by_id(target_user_id)

        if commit:
            await self._uow.commit()
