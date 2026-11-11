from uuid import UUID

from src.core.domain.enums import SystemRole
from src.core.protocols import IPasswordHasher, IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.application.dto import ChangePasswordAdminCommand
from src.modules.users.domain.exceptions import (
    SelfActionForbiddenError,
    SuperAdminActionForbiddenError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class ChangePasswordAdminUseCase:
    """Use Case встановлення або зміни пароля іншому користувачу"""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        password_hasher: IPasswordHasher,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._hasher = password_hasher

    async def execute(
        self,
        actor: CurrentUser,
        target_user_id: UUID,
        cmd: ChangePasswordAdminCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Змінює або первинно встановлює пароль облікового запису іншого користувача."""
        if actor.id == target_user_id:
            raise SelfActionForbiddenError("Заборонено змінювати пароль собі.")

        target_user = await self._user_repo.get_by_id(target_user_id)
        if target_user is None:
            raise UserNotFoundError(f"Користувача з ID {target_user_id} не знайдено.")

        target_user.ensure_active("змінити пароль")

        check_version(
            actual_version=target_user.version,
            expected_version=cmd.version,
            entity_title="користувача",
        )

        if target_user.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminActionForbiddenError("Заборонено змінювати пароль суперадміністратора.")

        new_hash = self._hasher.hash(cmd.new_password)
        target_user.change_password(new_hash)
        await self._user_repo.save(target_user)

        if commit:
            await self._uow.commit()
