from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.application.dto import UpdateMyTelegramAccountCommand
from src.modules.users.domain.exceptions import (
    TelegramAccountNotLinkedError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class UpdateMyTelegramAccountUseCase:
    """Use Case оновлення власних візуальних реквізитів Telegram користувачем"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: UUID,
        cmd: UpdateMyTelegramAccountCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Оновлює візуальні поля tg_username та tg_full_name прив'язаного Telegram-профілю."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        user.ensure_active("оновити профіль Telegram")

        if user.telegram_account is None:
            raise TelegramAccountNotLinkedError("У користувача немає прив'язаного Telegram-профілю.")

        check_version(
            actual_version=user.telegram_account.version,
            expected_version=cmd.version,
            entity_title="Telegram-акаунта",
        )

        user.telegram_account.update_visual_profile(
            tg_username=cmd.tg_username,
            tg_full_name=cmd.tg_full_name,
        )
        await self._user_repo.save(user)

        if commit:
            await self._uow.commit()
