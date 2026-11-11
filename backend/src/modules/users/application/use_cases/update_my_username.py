from uuid import UUID

from src.core.protocols import IUnitOfWork
from src.modules.users.application.dto import UpdateMyUsernameCommand
from src.modules.users.domain.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class UpdateMyUsernameUseCase:
    """Use Case зміни власного логіна користувачем"""

    def __init__(self, uow: IUnitOfWork, user_repo: IUserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: UUID,
        cmd: UpdateMyUsernameCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Оновлює логін облікового запису поточного користувача."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        user.ensure_active("змінити логін")

        check_version(
            actual_version=user.version,
            expected_version=cmd.version,
            entity_title="користувача",
        )

        if cmd.username != user.username:
            if await self._user_repo.exists_by_username(cmd.username):
                raise UserAlreadyExistsError(f"Логін '{cmd.username}' вже зайнятий.")
            user.change_username(cmd.username)
            await self._user_repo.save(user)

        if commit:
            await self._uow.commit()
