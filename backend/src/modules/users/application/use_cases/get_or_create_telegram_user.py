from uuid import UUID

from uuid6 import uuid7

from src.core.domain.enums import SystemRole
from src.core.protocols import IUnitOfWork
from src.modules.users.application.dto import RegisterTelegramUserCommand
from src.modules.users.domain.exceptions import UserDeactivatedError
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User


class GetOrCreateTelegramUserUseCase:
    """Use Case синхронізації або створення користувача при команді /start"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        cmd: RegisterTelegramUserCommand,
        *,
        commit: bool = True,
    ) -> UUID:
        """
        Знаходить існуючого користувача за Telegram ID або атомарно створює нового.

        Заборонено автоматично відновлювати деактивованого користувача.
        """
        user = await self._user_repo.get_by_telegram_id(cmd.telegram_id)

        if user is not None:
            # Захист: якщо адміністратор деактивував користувача, /start не повинен його розблокувати
            if not user.is_active:
                raise UserDeactivatedError("Обліковий запис деактивовано. Зверніться до адміністратора.")

            user.link_or_update_telegram(
                telegram_id=cmd.telegram_id,
                telegram_chat_id=cmd.telegram_chat_id,
                tg_username=cmd.tg_username,
                tg_full_name=cmd.tg_full_name,
            )
            await self._user_repo.save(user)
        else:
            # Логін суворо за шаблоном tg_{telegram_id}
            chosen_username = f"tg_{cmd.telegram_id}"
            if await self._user_repo.exists_by_username(chosen_username):
                chosen_username = f"tg_{cmd.telegram_id}_{uuid7().hex[:6]}"

            user = User(
                id=uuid7(),
                username=chosen_username,
                role=SystemRole.USER,
                password_hash=None,
            )
            user.link_or_update_telegram(
                telegram_id=cmd.telegram_id,
                telegram_chat_id=cmd.telegram_chat_id,
                tg_username=cmd.tg_username,
                tg_full_name=cmd.tg_full_name,
            )
            await self._user_repo.save(user)

        if commit:
            await self._uow.commit()

        return user.id
