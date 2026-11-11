from uuid import UUID

from uuid6 import uuid7

from src.core.domain.enums import SystemRole
from src.core.exceptions import ForbiddenException
from src.core.protocols import IPasswordHasher, IUnitOfWork
from src.core.security import CurrentUser
from src.modules.users.application.dto import CreateUserCommand
from src.modules.users.domain.exceptions import (
    SuperAdminAlreadyExistsError,
    UserAlreadyExistsError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User


class CreateUserUseCase:
    """Use Case створення нового користувача"""

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
        creator: CurrentUser,
        cmd: CreateUserCommand,
        *,
        commit: bool = True,
    ) -> UUID:
        """Реєструє нового користувача в системі з перевіркою ієрархії ролей RBAC."""
        # Правило: в системі не може бути більше одного SuperAdmin
        if cmd.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminAlreadyExistsError("Створення користувача з роллю SuperAdmin заборонено.")

        # Правило: Admin може створити тільки USER
        if creator.role == SystemRole.ADMIN and cmd.role != SystemRole.USER:
            raise ForbiddenException("Адміністратор може створювати користувачів тільки з роллю USER.")

        # Перевірка унікальності логіна
        if await self._user_repo.exists_by_username(cmd.username):
            raise UserAlreadyExistsError(f"Користувач з логіном '{cmd.username}' вже існує.")

        # Хешування пароля, якщо він переданий
        password_hash = self._hasher.hash(cmd.password) if cmd.password else None

        user_id = uuid7()
        user = User(
            id=user_id,
            username=cmd.username,
            role=cmd.role,
            password_hash=password_hash,
        )

        # Застосування початкових налаштувань
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

        return user.id
