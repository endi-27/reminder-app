from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.protocols import IUnitOfWork
from src.core.security import CurrentUser
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.modules.users.application.dto import RegisterTelegramUserCommand
from src.modules.users.application.use_cases.get_or_create_telegram_user import (
    GetOrCreateTelegramUserUseCase,
)
from src.modules.users.infrastructure.repository import SqlAlchemyUserRepository
from src.modules.users.queries.dto import (
    UserNotificationContextDTO,
    UserResponseDTO,
    UserSettingsResponseDTO,
)
from src.modules.users.queries.query_service import UserQueryService


class UsersPublicGateway:
    """
    Публічний фасад модуля користувачів для міжмодульної взаємодії (Інваріант 1).

    Інкапсулює операції читання та реєстрації користувачів з інших доменних модулів.
    """

    def __init__(
        self,
        session: AsyncSession,
        uow: IUnitOfWork | None = None,
    ) -> None:
        self._session = session
        self._external_uow = uow
        self._uow = uow or SqlAlchemyUnitOfWork(session=session)
        self._query_service = UserQueryService(session=session)
        self._user_repo = SqlAlchemyUserRepository(session=session)

    async def get_user_by_id(self, user_id: UUID) -> UserResponseDTO | None:
        """Отримання профілю користувача за ID."""
        return await self._query_service.get_by_id(user_id)

    async def get_user_by_telegram_id(self, telegram_id: int) -> UserResponseDTO | None:
        """Отримання профілю користувача за Telegram ID."""
        return await self._query_service.get_by_telegram_id(telegram_id)

    async def get_user_settings(self, user_id: UUID) -> UserSettingsResponseDTO | None:
        """Отримання параметрів налаштувань користувача."""
        return await self._query_service.get_settings_by_user_id(user_id)

    async def get_notification_context(self, user_id: UUID) -> UserNotificationContextDTO | None:
        """Отримання контексту сповіщень користувача для шедулера."""
        return await self._query_service.get_notification_context(user_id)

    async def get_notification_contexts_by_ids(
        self,
        user_ids: Sequence[UUID],
    ) -> dict[UUID, UserNotificationContextDTO]:
        """Пакетне завантаження контекстів сповіщень користувачів без N+1."""
        return await self._query_service.get_notification_contexts_by_ids(user_ids)

    async def get_or_register_telegram_user(
        self,
        cmd: RegisterTelegramUserCommand,
    ) -> UserResponseDTO:
        """
        Знаходить або реєструє користувача з Telegram.

        Якщо фасад викликано в рамках зовнішньої транзакції (передано зовнішній uow),
        коміт залишається за ініціатором транзакції (Інваріант 7).
        """
        use_case = GetOrCreateTelegramUserUseCase(
            uow=self._uow,
            user_repo=self._user_repo,
        )
        should_commit = self._external_uow is None
        user = await use_case.execute(cmd, commit=should_commit)

        user_dto = await self._query_service.get_by_id(user.id)
        if user_dto is None:
            raise RuntimeError(f"Не вдалося завантажити зареєстрованого користувача з ID {user.id}.")
        return user_dto


async def resolve_user_by_telegram_id(
    telegram_id: int,
    session: AsyncSession,
) -> CurrentUser | None:
    """
    Резолвер авторизаційного контексту CurrentUser за числовим Telegram ID.

    Використовується глобальним механізмом автентифікації без прямих циклічних імпортів.
    """
    query_service = UserQueryService(session)
    user_dto = await query_service.get_by_telegram_id(telegram_id)
    if user_dto is None:
        return None

    return CurrentUser(
        id=user_dto.id,
        username=user_dto.username,
        role=user_dto.role,
        telegram_id=telegram_id,
    )


__all__ = [
    "UsersPublicGateway",
    "resolve_user_by_telegram_id",
]
