from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.domain.exceptions import (
    TelegramAccountInUseError,
    TelegramAccountNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository


class HardDeleteTelegramAccountUseCase:
    """Use Case остаточного фізичного видалення відв'язаного профілю Telegram"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        account_id: UUID,
        *,
        commit: bool = True,
    ) -> None:
        """Видаляє запис Telegram-акаунта суворо за умови, що він не прив'язаний до користувача."""
        account = await self._user_repo.get_telegram_account_by_id(account_id)
        if account is None:
            raise TelegramAccountNotFoundError("Зазначений Telegram-профіль не знайдено.")

        if account.user_id is not None:
            raise TelegramAccountInUseError(
                "Заборонено видаляти Telegram-профіль, коли він прив'язаний до користувача."
            )

        await self._user_repo.delete_telegram_account_by_id(account_id)

        if commit:
            await self._uow.commit()
