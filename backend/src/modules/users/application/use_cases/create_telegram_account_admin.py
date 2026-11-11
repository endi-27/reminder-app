from uuid import UUID

from uuid6 import uuid7

from src.core.exceptions import ForbiddenException
from src.core.protocols import IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.application.dto import CreateTelegramAccountAdminCommand
from src.modules.users.domain.exceptions import (
    TelegramAccountAlreadyExistsError,
    TelegramAccountAlreadyLinkedError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import UserTelegramAccount


class CreateTelegramAccountAdminUseCase:
    """Use Case ручного створення запису Telegram-акаунта адміністратором (тільки SuperAdmin)."""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        actor: CurrentUser,
        cmd: CreateTelegramAccountAdminCommand,
        *,
        commit: bool = True,
    ) -> UUID:
        """Створює запис у таблиці user_telegram_accounts"""
        if not actor.is_super_admin:
            raise ForbiddenException("Тільки SuperAdmin має право створювати записи Telegram-акаунтів.")

        # Перевірка унікальності telegram_id
        if await self._user_repo.get_telegram_account_by_tg_id(cmd.telegram_id) is not None:
            raise TelegramAccountAlreadyExistsError(
                f"Telegram-акаунт з telegram_id {cmd.telegram_id} вже зареєстровано в системі."
            )

        # Перевірка унікальності telegram_chat_id
        if await self._user_repo.get_telegram_account_by_chat_id(cmd.telegram_chat_id) is not None:
            raise TelegramAccountAlreadyExistsError(
                f"Telegram-акаунт з telegram_chat_id {cmd.telegram_chat_id} вже зареєстровано в системі."
            )

        # Створення запису з опціональною прив'язкою до користувача
        db_record_id = uuid7()
        if cmd.user_id is not None:
            user = await self._user_repo.get_by_id(cmd.user_id)
            if user is None:
                raise UserNotFoundError(f"Користувача з ID {cmd.user_id} не знайдено.")

            user.ensure_active("створити та прив'язати Telegram-акаунт")

            if user.telegram_account is not None:
                raise TelegramAccountAlreadyLinkedError(
                    f"Користувач '{user.username}' вже має прив'язаний Telegram-акаунт."
                )

            account = UserTelegramAccount(
                id=db_record_id,
                user_id=cmd.user_id,
                telegram_id=cmd.telegram_id,
                telegram_chat_id=cmd.telegram_chat_id,
                tg_username=cmd.tg_username,
                tg_full_name=cmd.tg_full_name,
                version=1,
            )
            user.telegram_account = account
            await self._user_repo.save(user)
        else:
            account = UserTelegramAccount(
                id=db_record_id,
                user_id=None,
                telegram_id=cmd.telegram_id,
                telegram_chat_id=cmd.telegram_chat_id,
                tg_username=cmd.tg_username,
                tg_full_name=cmd.tg_full_name,
                version=1,
            )
            await self._user_repo.save_telegram_account(account)

        if commit:
            await self._uow.commit()

        return account.id
