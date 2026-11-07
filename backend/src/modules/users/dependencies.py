from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_uow
from src.core.database import get_db_session
from src.core.protocols import IPasswordHasher, IUnitOfWork
from src.core.security import default_password_hasher
from src.modules.users.application.use_cases import (
    AuthenticateUserUseCase,
    CreateUserUseCase,
    GetOrCreateTelegramUserUseCase,
    HardDeleteUserUseCase,
    SoftDeleteUserUseCase,
    UpdateUserSettingsUseCase,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.infrastructure.repository import SqlAlchemyUserRepository
from src.modules.users.public import UsersPublicGateway
from src.modules.users.queries.query_service import UserQueryService


def get_password_hasher() -> IPasswordHasher:
    """Отримання інстансу хешера паролів."""
    return default_password_hasher


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IUserRepository:
    """Фабрика створення репозиторію користувачів."""
    return SqlAlchemyUserRepository(session)


def get_user_query_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserQueryService:
    """Фабрика створення CQRS Read-Side сервісу запитів користувачів."""
    return UserQueryService(session)


def get_authenticate_user_use_case(
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    password_hasher: Annotated[IPasswordHasher, Depends(get_password_hasher)],
) -> AuthenticateUserUseCase:
    """Фабрика Use Case автентифікації користувача."""
    return AuthenticateUserUseCase(user_repo=user_repo, password_hasher=password_hasher)


def get_create_user_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    password_hasher: Annotated[IPasswordHasher, Depends(get_password_hasher)],
) -> CreateUserUseCase:
    """Фабрика Use Case створення нового користувача."""
    return CreateUserUseCase(uow=uow, user_repo=user_repo, password_hasher=password_hasher)


def get_get_or_create_telegram_user_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> GetOrCreateTelegramUserUseCase:
    """Фабрика Use Case синхронізації профілю користувача з Telegram."""
    return GetOrCreateTelegramUserUseCase(uow=uow, user_repo=user_repo)


def get_update_user_settings_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UpdateUserSettingsUseCase:
    """Фабрика Use Case точкового оновлення налаштувань користувача."""
    return UpdateUserSettingsUseCase(uow=uow, user_repo=user_repo)


def get_soft_delete_user_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> SoftDeleteUserUseCase:
    """Фабрика Use Case м'якого видалення користувача."""
    return SoftDeleteUserUseCase(uow=uow, user_repo=user_repo)


def get_hard_delete_user_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> HardDeleteUserUseCase:
    """Фабрика Use Case фізичного видалення користувача."""
    return HardDeleteUserUseCase(uow=uow, user_repo=user_repo)


def get_users_public_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
) -> UsersPublicGateway:
    """Фабрика публічного фасаду модуля користувачів."""
    return UsersPublicGateway(session=session, uow=uow)
