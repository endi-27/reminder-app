from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.domain.exceptions import (
    TelegramAccountNotLinkedError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository


class UnlinkTelegramAccountUseCase:
    """Use Case відв'язування Telegram-акаунта від користувача"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: UUID,
        *,
        commit: bool = True,
    ) -> None:
        """Відв'язує профіль Telegram від користувача зі збереженням запису вільним."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        user.ensure_active("відв'язати Telegram-акаунт")

        if user.telegram_account is None:
            raise TelegramAccountNotLinkedError("У користувача немає прив'язаного Telegram-профілю.")

        unlinked_account = user.unlink_telegram()
        await self._user_repo.save(user)

        if unlinked_account is not None:
            await self._user_repo.save_telegram_account(unlinked_account)

        if commit:
            await self._uow.commit()
