from uuid6 import uuid7

from src.core.protocols import IPasswordHasher, IUnitOfWork
from src.modules.users.application.dto import CreateUserCommand
from src.modules.users.domain.exceptions import UserAlreadyExistsError
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User


class CreateUserUseCase:
    """Use Case створення нового користувача з валідацією унікальності логіна."""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        password_hasher: IPasswordHasher,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._hasher = password_hasher

    async def execute(self, cmd: CreateUserCommand, *, commit: bool = True) -> User:
        """Реєструє нового користувача в системі."""
        if await self._user_repo.exists_by_username(cmd.username):
            raise UserAlreadyExistsError(f"Користувач з логіном '{cmd.username}' вже існує.")

        password_hash = self._hasher.hash(cmd.password) if cmd.password else None

        user = User(
            id=uuid7(),
            username=cmd.username,
            role=cmd.role,
            password_hash=password_hash,
        )
        user.update_settings(timezone=cmd.timezone)

        await self._user_repo.save(user)

        if commit:
            await self._uow.commit()

        return user
