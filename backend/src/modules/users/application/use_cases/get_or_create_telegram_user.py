from uuid6 import uuid7

from src.core.protocols import IUnitOfWork
from src.modules.users.application.dto import RegisterTelegramUserCommand
from src.modules.users.domain.enums import UserRole
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User


class GetOrCreateTelegramUserUseCase:
    """Use Case синхронізації профілю та реєстрації користувача з Telegram-бота."""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        cmd: RegisterTelegramUserCommand,
        *,
        commit: bool = True,
    ) -> User:
        """
        Знаходить існуючого користувача за Telegram ID або створює нового.

        Оновлює інформацію про чат, нікнейм та повне ім'я користувача.
        """
        user = await self._user_repo.get_by_telegram_id(cmd.telegram_id, include_deleted=True)

        if user is not None:
            if not user.is_active:
                user.restore()
            user.link_or_update_telegram(
                telegram_id=cmd.telegram_id,
                telegram_chat_id=cmd.telegram_chat_id,
                tg_username=cmd.tg_username,
                tg_full_name=cmd.tg_full_name,
            )
            await self._user_repo.save(user)
        else:
            base_username = cmd.tg_username or f"tg_{cmd.telegram_id}"
            chosen_username = base_username

            if await self._user_repo.exists_by_username(chosen_username):
                chosen_username = f"{cmd.tg_username or 'tg'}_{cmd.telegram_id}"
                if await self._user_repo.exists_by_username(chosen_username):
                    chosen_username = f"tg_{cmd.telegram_id}_{uuid7().hex[:6]}"

            user = User(
                id=uuid7(),
                username=chosen_username,
                role=UserRole.USER,
                password_hash=None,
            )
            user.update_settings(timezone=cmd.timezone)
            user.link_or_update_telegram(
                telegram_id=cmd.telegram_id,
                telegram_chat_id=cmd.telegram_chat_id,
                tg_username=cmd.tg_username,
                tg_full_name=cmd.tg_full_name,
            )
            await self._user_repo.save(user)

        if commit:
            await self._uow.commit()

        return user
