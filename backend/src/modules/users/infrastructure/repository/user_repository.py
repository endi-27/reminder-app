from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.base import ExecutableOption

from src.core.domain.enums import SystemRole
from src.infrastructure.db.repositories import SqlAlchemyBaseCrudRepository
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User, UserTelegramAccount
from src.modules.users.infrastructure.mappers import TelegramAccountMapper, UserMapper
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
    ) -> User | None:
        """Пошук користувача за унікальним логіном."""
        stmt = select(UserModel).options(*self._default_options()).where(UserModel.username == username)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm is not None else None

    async def get_by_telegram_id(
        self,
        telegram_id: int,
    ) -> User | None:
        """Пошук користувача за Telegram ID через зв'язок 1:1 з user_telegram_accounts."""
        stmt = (
            select(UserModel)
            .join(UserModel.telegram_account)
            .options(*self._default_options())
            .where(UserTelegramAccountModel.telegram_id == telegram_id)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm is not None else None

    async def exists_by_username(self, username: str) -> bool:
        """Перевірка наявності користувача з вказаним логіном (включаючи видалених)."""
        stmt = select(1).where(UserModel.username == username).limit(1)
        result = await self._session.execute(stmt)
        return bool(result.scalar() is not None)

    async def exists_super_admin(self) -> bool:
        """Перевірка наявності активного користувача з роллю SUPER_ADMIN."""
        stmt = (
            select(1)
            .where(
                UserModel.role == SystemRole.SUPER_ADMIN,
                UserModel.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return bool(result.scalar() is not None)

    async def get_telegram_account_by_id(self, account_id: UUID) -> UserTelegramAccount | None:
        """Пошук профілю Telegram за первинним ключем."""
        stmt = select(UserTelegramAccountModel).where(UserTelegramAccountModel.id == account_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return TelegramAccountMapper().to_domain(orm) if orm is not None else None

    async def get_telegram_account_by_tg_id(self, telegram_id: int) -> UserTelegramAccount | None:
        """Пошук профілю Telegram за числовим ідентифікатором Telegram ID."""
        stmt = select(UserTelegramAccountModel).where(UserTelegramAccountModel.telegram_id == telegram_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return TelegramAccountMapper().to_domain(orm) if orm is not None else None

    async def get_telegram_account_by_chat_id(self, chat_id: int) -> UserTelegramAccount | None:
        """Пошук профілю Telegram за ідентифікатором чату Telegram Chat ID."""
        stmt = select(UserTelegramAccountModel).where(UserTelegramAccountModel.telegram_chat_id == chat_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return TelegramAccountMapper().to_domain(orm) if orm is not None else None

    async def save_telegram_account(self, account: UserTelegramAccount, /) -> None:
        """Збереження або оновлення запису профілю Telegram."""
        stmt = select(UserTelegramAccountModel).where(UserTelegramAccountModel.id == account.id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()

        if orm is not None:
            orm.user_id = account.user_id
            orm.telegram_id = account.telegram_id
            orm.telegram_chat_id = account.telegram_chat_id
            orm.tg_username = account.tg_username
            orm.tg_full_name = account.tg_full_name
            orm.version = account.version
        else:
            new_orm = TelegramAccountMapper().to_model(account)
            self._session.add(new_orm)

        await self._session.flush()

    async def delete_telegram_account_by_id(self, account_id: UUID, /) -> bool:
        """Фізичне видалення (Hard Delete) профілю Telegram."""
        stmt = delete(UserTelegramAccountModel).where(UserTelegramAccountModel.id == account_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount > 0)
