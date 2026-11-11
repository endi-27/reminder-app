from uuid import UUID

from src.core.domain.enums import SystemRole
from src.core.protocols import IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.application.dto import UpdateUserSettingsCommand
from src.modules.users.domain.exceptions import (
    SelfActionForbiddenError,
    SuperAdminActionForbiddenError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class UpdateOtherUserSettingsUseCase:
    """Use Case зміни налаштувань іншому користувачу адміністратором"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        actor: CurrentUser,
        target_user_id: UUID,
        cmd: UpdateUserSettingsCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Оновлює налаштування іншого користувача"""
        if actor.id == target_user_id:
            raise SelfActionForbiddenError("Заборонено змінювати налаштування собі.")

        target_user = await self._user_repo.get_by_id(target_user_id)
        if target_user is None:
            raise UserNotFoundError(f"Користувача з ID {target_user_id} не знайдено.")

        target_user.ensure_active("змінити налаштування")

        if target_user.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminActionForbiddenError("Заборонено змінювати налаштування суперадміністратора.")

        check_version(
            actual_version=target_user.current_settings.version,
            expected_version=cmd.version,
            entity_title="налаштувань користувача",
        )

        target_user.update_settings(
            timezone=cmd.timezone,
            quiet_hours_start=cmd.quiet_hours_start,
            quiet_hours_end=cmd.quiet_hours_end,
            preferred_bank=cmd.preferred_bank,
            auto_deadline_priority_escalation=cmd.auto_deadline_priority_escalation,
        )
        await self._user_repo.save(target_user)

        if commit:
            await self._uow.commit()
