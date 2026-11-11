from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.application.dto import UpdateTelegramAccountAdminCommand
from src.modules.users.domain.exceptions import (
    SelfActionForbiddenError,
    TelegramAccountAlreadyLinkedError,
    TelegramAccountNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class UpdateTelegramAccountAdminUseCase:
    """Use Case зміни даних профілю Telegram"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        actor: CurrentUser,
        account_id: UUID,
        cmd: UpdateTelegramAccountAdminCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Оновлює реквізити Telegram-акаунта"""
        account = await self._user_repo.get_telegram_account_by_id(account_id)
        if account is None:
            raise TelegramAccountNotFoundError("Зазначений Telegram-профіль не знайдено.")

        # Якщо профіль прив'язаний до користувача, який виконує запит -> відхиляється
        if account.user_id is not None and account.user_id == actor.id:
            raise SelfActionForbiddenError("Заборонено змінювати технічні реквізити власного Telegram-акаунта.")

        check_version(
            actual_version=account.version,
            expected_version=cmd.version,
            entity_title="Telegram-акаунта",
        )

        if cmd.telegram_id is not None and cmd.telegram_id != account.telegram_id:
            existing = await self._user_repo.get_telegram_account_by_tg_id(cmd.telegram_id)
            if existing is not None and existing.id != account.id:
                raise TelegramAccountAlreadyLinkedError(f"Telegram ID {cmd.telegram_id} вже зайнятий іншим профілем.")

        account.update_profile(
            telegram_id=cmd.telegram_id,
            telegram_chat_id=cmd.telegram_chat_id,
            tg_username=cmd.tg_username,
            tg_full_name=cmd.tg_full_name,
        )
        await self._user_repo.save_telegram_account(account)

        if commit:
            await self._uow.commit()
