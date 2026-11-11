from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.application.dto import LinkTelegramAccountCommand
from src.modules.users.domain.exceptions import (
    TelegramAccountAlreadyLinkedError,
    TelegramAccountNotFoundError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class LinkTelegramAccountUseCase:
    """Use Case прив'язки Telegram-акаунта до користувача"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: UUID,
        cmd: LinkTelegramAccountCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Прив'язує вільний Telegram-акаунт до користувача з дотриманням правила 1:1."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        user.ensure_active("прив'язати Telegram-акаунт")

        check_version(
            actual_version=user.version,
            expected_version=cmd.version,
            entity_title="користувача",
        )

        if user.telegram_account is not None:
            raise TelegramAccountAlreadyLinkedError("У цього користувача вже є прив'язаний Telegram-профіль.")

        account = await self._user_repo.get_telegram_account_by_id(cmd.telegram_account_id)
        if account is None:
            raise TelegramAccountNotFoundError("Зазначений Telegram-профіль не знайдено.")

        if account.user_id is not None:
            raise TelegramAccountAlreadyLinkedError("Цей Telegram-профіль вже прив'язаний до іншого користувача.")

        user.link_telegram_account(account)
        await self._user_repo.save(user)
        await self._user_repo.save_telegram_account(account)

        if commit:
            await self._uow.commit()
