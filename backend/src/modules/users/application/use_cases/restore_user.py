from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.domain.exceptions import UserNotFoundError
from src.modules.users.domain.interfaces import IUserRepository


class RestoreUserUseCase:
    """Use Case відновлення деактивованого користувача"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        target_user_id: UUID,
        *,
        commit: bool = True,
    ) -> None:
        """Відновлює м'яко видаленого користувача."""
        user = await self._user_repo.get_by_id(target_user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {target_user_id} не знайдено.")

        user.restore()
        await self._user_repo.save(user)

        if commit:
            await self._uow.commit()
