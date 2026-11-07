from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.base import ExecutableOption

from src.infrastructure.db.repositories import SqlAlchemyBaseCrudRepository
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User
from src.modules.users.infrastructure.mappers import UserMapper
from src.modules.users.infrastructure.models import (
    UserModel,
    UserTelegramAccountModel,
)


class SqlAlchemyUserRepository(
    SqlAlchemyBaseCrudRepository[User, UserModel],
    IUserRepository,
):
    """Репозиторій користувачів на базі SQLAlchemy 2.0."""

    _model_cls = UserModel
    _mapper = UserMapper

    def _default_options(self) -> Sequence[ExecutableOption]:
        """Опції жадібного завантаження зв'язаних профілю Telegram та налаштувань."""
        return (
            joinedload(UserModel.telegram_account),
            joinedload(UserModel.settings),
        )

    async def get_by_username(
        self,
        username: str,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        """Пошук користувача за унікальним логіном."""
        stmt = select(UserModel).options(*self._default_options()).where(UserModel.username == username)
        if not include_deleted:
            stmt = self._apply_active_filter(stmt)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm is not None else None

    async def get_by_telegram_id(
        self,
        telegram_id: int,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        """Пошук користувача за Telegram ID через зв'язок 1:1 з user_telegram_accounts."""
        stmt = (
            select(UserModel)
            .join(UserModel.telegram_account)
            .options(*self._default_options())
            .where(UserTelegramAccountModel.telegram_id == telegram_id)
        )
        if not include_deleted:
            stmt = self._apply_active_filter(stmt)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm is not None else None

    async def exists_by_username(self, username: str) -> bool:
        """Перевірка наявності користувача з вказаним логіном (включаючи видалених)."""
        stmt = select(1).where(UserModel.username == username).limit(1)
        result = await self._session.execute(stmt)
        return bool(result.scalar() is not None)
