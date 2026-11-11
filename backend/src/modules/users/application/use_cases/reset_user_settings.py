from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.domain.exceptions import UserNotFoundError
from src.modules.users.domain.interfaces import IUserRepository


class ResetUserSettingsUseCase:
    """Use Case скидання власних налаштувань користувача до значень за замовчуванням"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: UUID,
        *,
        commit: bool = True,
    ) -> None:
        """Скидає параметри налаштувань поточного користувача до дефолтів."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        user.ensure_active("скинути налаштування")
        user.reset_settings()
        await self._user_repo.save(user)

        if commit:
            await self._uow.commit()
