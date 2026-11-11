from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_uow
from src.core.database import get_db_session
from src.core.protocols import IPasswordHasher, IUnitOfWork
from src.core.security import default_password_hasher
from src.modules.users.application.use_cases import (
    AuthenticateUserUseCase,
    ChangeMyPasswordUseCase,
    ChangePasswordAdminUseCase,
    CreateTelegramAccountAdminUseCase,
    CreateUserUseCase,
    GetOrCreateTelegramUserUseCase,
    HardDeleteTelegramAccountUseCase,
    HardDeleteUserUseCase,
    LinkTelegramAccountUseCase,
    ResetUserSettingsUseCase,
    RestoreUserUseCase,
    SoftDeleteUserUseCase,
    UnlinkTelegramAccountUseCase,
    UpdateMyTelegramAccountUseCase,
    UpdateMyUsernameUseCase,
    UpdateOtherUserSettingsUseCase,
    UpdateTelegramAccountAdminUseCase,
    UpdateUserProfileAdminUseCase,
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


def get_link_telegram_account_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> LinkTelegramAccountUseCase:
    """Фабрика Use Case прив'язки Telegram-акаунта."""
    return LinkTelegramAccountUseCase(uow=uow, user_repo=user_repo)


def get_unlink_telegram_account_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UnlinkTelegramAccountUseCase:
    """Фабрика Use Case відв'язування Telegram-акаунта."""
    return UnlinkTelegramAccountUseCase(uow=uow, user_repo=user_repo)


def get_change_password_admin_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    password_hasher: Annotated[IPasswordHasher, Depends(get_password_hasher)],
) -> ChangePasswordAdminUseCase:
    """Фабрика Use Case зміни пароля адміністратором."""
    return ChangePasswordAdminUseCase(uow=uow, user_repo=user_repo, password_hasher=password_hasher)


def get_change_my_password_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    password_hasher: Annotated[IPasswordHasher, Depends(get_password_hasher)],
) -> ChangeMyPasswordUseCase:
    """Фабрика Use Case зміни власного пароля."""
    return ChangeMyPasswordUseCase(uow=uow, user_repo=user_repo, password_hasher=password_hasher)


def get_update_user_profile_admin_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UpdateUserProfileAdminUseCase:
    """Фабрика Use Case оновлення профілю адміністратором."""
    return UpdateUserProfileAdminUseCase(uow=uow, user_repo=user_repo)


def get_update_my_username_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UpdateMyUsernameUseCase:
    """Фабрика Use Case оновлення власного логіна."""
    return UpdateMyUsernameUseCase(uow=uow, user_repo=user_repo)


def get_update_telegram_account_admin_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UpdateTelegramAccountAdminUseCase:
    """Фабрика Use Case оновлення Telegram-акаунта адміністратором."""
    return UpdateTelegramAccountAdminUseCase(uow=uow, user_repo=user_repo)


def get_create_telegram_account_admin_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> CreateTelegramAccountAdminUseCase:
    """Фабрика Use Case створення Telegram-акаунта адміністратором (SuperAdmin)."""
    return CreateTelegramAccountAdminUseCase(uow=uow, user_repo=user_repo)


def get_update_my_telegram_account_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UpdateMyTelegramAccountUseCase:
    """Фабрика Use Case оновлення візуальних даних свого Telegram-акаунта."""
    return UpdateMyTelegramAccountUseCase(uow=uow, user_repo=user_repo)


def get_update_other_user_settings_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UpdateOtherUserSettingsUseCase:
    """Фабрика Use Case оновлення налаштувань іншому користувачу."""
    return UpdateOtherUserSettingsUseCase(uow=uow, user_repo=user_repo)


def get_update_user_settings_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> UpdateUserSettingsUseCase:
    """Фабрика Use Case точкового оновлення налаштувань користувача."""
    return UpdateUserSettingsUseCase(uow=uow, user_repo=user_repo)


def get_reset_user_settings_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> ResetUserSettingsUseCase:
    """Фабрика Use Case скидання налаштувань до значень за замовчуванням."""
    return ResetUserSettingsUseCase(uow=uow, user_repo=user_repo)


def get_soft_delete_user_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SoftDeleteUserUseCase:
    """Фабрика Use Case м'якого видалення користувача (з паузою дедлайн-задач)."""
    from src.modules.reminders.public import RemindersPublicGateway

    reminders_gateway = RemindersPublicGateway(session=session, uow=uow)
    return SoftDeleteUserUseCase(uow=uow, user_repo=user_repo, reminders_gateway=reminders_gateway)


def get_restore_user_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> RestoreUserUseCase:
    """Фабрика Use Case відновлення деактивованого користувача."""
    return RestoreUserUseCase(uow=uow, user_repo=user_repo)


def get_hard_delete_user_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> HardDeleteUserUseCase:
    """Фабрика Use Case фізичного видалення користувача."""
    return HardDeleteUserUseCase(uow=uow, user_repo=user_repo)


def get_hard_delete_telegram_account_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> HardDeleteTelegramAccountUseCase:
    """Фабрика Use Case фізичного видалення відв'язаного профілю Telegram."""
    return HardDeleteTelegramAccountUseCase(uow=uow, user_repo=user_repo)


def get_users_public_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
) -> UsersPublicGateway:
    """Фабрика публічного фасаду модуля користувачів."""
    return UsersPublicGateway(session=session, uow=uow)
