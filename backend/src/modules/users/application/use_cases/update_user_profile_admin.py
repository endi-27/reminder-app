from uuid import UUID

from src.core.domain.enums import SystemRole
from src.core.protocols import IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.application.dto import UpdateUserProfileAdminCommand
from src.modules.users.domain.exceptions import (
    SelfActionForbiddenError,
    SuperAdminActionForbiddenError,
    SuperAdminAlreadyExistsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class UpdateUserProfileAdminUseCase:
    """Use Case зміни логіна та ролі іншому користувачу"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        actor: CurrentUser,
        target_user_id: UUID,
        cmd: UpdateUserProfileAdminCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Оновлює системні реквізити користувача."""
        if actor.id == target_user_id:
            raise SelfActionForbiddenError("Заборонено змінювати власний профіль.")

        target_user = await self._user_repo.get_by_id(target_user_id)
        if target_user is None:
            raise UserNotFoundError(f"Користувача з ID {target_user_id} не знайдено.")

        target_user.ensure_active("оновити профіль")

        check_version(
            actual_version=target_user.version,
            expected_version=cmd.version,
            entity_title="користувача",
        )

        if target_user.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminActionForbiddenError("Заборонено змінювати дані суперадміністратора.")

        if cmd.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminAlreadyExistsError("Призначення ролі SuperAdmin заборонено.")

        if cmd.username is not None and cmd.username != target_user.username:
            if await self._user_repo.exists_by_username(cmd.username):
                raise UserAlreadyExistsError(f"Логін '{cmd.username}' вже використовується іншим користувачем.")
            target_user.change_username(cmd.username)

        if cmd.role is not None:
            target_user.change_role(cmd.role)

        await self._user_repo.save(target_user)

        if commit:
            await self._uow.commit()
