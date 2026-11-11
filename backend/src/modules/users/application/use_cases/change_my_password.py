from uuid import UUID

from src.core.protocols import IPasswordHasher, IUnitOfWork
from src.modules.users.application.dto import ChangeMyPasswordCommand
from src.modules.users.domain.exceptions import (
    InvalidCurrentPasswordError,
    PasswordNotSetError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.utils.occ import check_version


class ChangeMyPasswordUseCase:
    """Use Case зміни власного пароля користувачем"""

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
        user_id: UUID,
        cmd: ChangeMyPasswordCommand,
        *,
        commit: bool = True,
    ) -> None:
        """Змінює власний пароль облікового запису з обов'язковою перевіркою старого пароля."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")

        user.ensure_active("змінити пароль")

        check_version(
            actual_version=user.version,
            expected_version=cmd.version,
            entity_title="користувача",
        )

        if user.password_hash is None:
            raise PasswordNotSetError(
                "Пароль не встановлено. Зверніться до адміністратора для встановлення початкового пароля."
            )

        if not self._hasher.verify(cmd.current_password, user.password_hash):
            raise InvalidCurrentPasswordError("Вказано невірний поточний пароль.")

        new_hash = self._hasher.hash(cmd.new_password)
        user.change_password(new_hash)
        await self._user_repo.save(user)

        if commit:
            await self._uow.commit()
