from typing import TYPE_CHECKING
from uuid import UUID

from src.core.domain.enums import SystemRole
from src.core.protocols import IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.domain.exceptions import (
    SelfActionForbiddenError,
    SuperAdminActionForbiddenError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository

if TYPE_CHECKING:
    from src.modules.reminders.public import RemindersPublicGateway


class SoftDeleteUserUseCase:
    """Use Case м'якої деактивації облікового запису користувача"""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        reminders_gateway: "RemindersPublicGateway | None" = None,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._reminders_gateway = reminders_gateway

    async def execute(
        self,
        actor: CurrentUser,
        target_user_id: UUID,
        *,
        commit: bool = True,
    ) -> None:
        """Позначає користувача як видаленого та автоматично призупиняє всі активні нагадування"""
        if actor.id == target_user_id:
            raise SelfActionForbiddenError("Заборонено деактивовувати власний обліковий запис.")

        user = await self._user_repo.get_by_id(target_user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {target_user_id} не знайдено.")

        if user.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminActionForbiddenError("Обліковий запис SuperAdmin не може бути деактивований.")

        user.soft_delete()
        await self._user_repo.save(user)

        # Автоматичне переведення всіх активних нагадувань у PAUSED при блокуванні користувача
        if self._reminders_gateway is not None:
            await self._reminders_gateway.pause_all_active_reminders_by_user_id(target_user_id, uow=self._uow)

        if commit:
            await self._uow.commit()
