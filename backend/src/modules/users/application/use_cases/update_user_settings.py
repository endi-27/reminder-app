from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.application.dto import UpdateUserSettingsCommand
from src.modules.users.domain.exceptions import UserNotFoundError
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class UpdateUserSettingsUseCase:
    """Use Case точкового оновлення параметрів користувача."""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: UUID,
        cmd: UpdateUserSettingsCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Оновлює налаштування користувача."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        user.ensure_active("оновити налаштування")

        check_version(
            actual_version=user.current_settings.version,
            expected_version=cmd.version,
            entity_title="налаштувань користувача",
        )

        user.update_settings(
            timezone=cmd.timezone,
            quiet_hours_start=cmd.quiet_hours_start,
            quiet_hours_end=cmd.quiet_hours_end,
            preferred_bank=cmd.preferred_bank,
            auto_deadline_priority_escalation=cmd.auto_deadline_priority_escalation,
        )

        await self._user_repo.save(user)

        if commit:
            await self._uow.commit()
