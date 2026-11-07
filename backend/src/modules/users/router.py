from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.api.dependencies import (
    CurrentUserDep,
    require_role,
    verify_bot_internal_token,
)
from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.core.security import CurrentUser, SystemRole
from src.modules.users.application.dto import (
    LoginCommand,
    RegisterTelegramUserCommand,
    TokenResponseDTO,
    UpdateUserSettingsCommand,
)
from src.modules.users.application.use_cases import (
    AuthenticateUserUseCase,
    GetOrCreateTelegramUserUseCase,
    HardDeleteUserUseCase,
    SoftDeleteUserUseCase,
    UpdateUserSettingsUseCase,
)
from src.modules.users.dependencies import (
    get_authenticate_user_use_case,
    get_get_or_create_telegram_user_use_case,
    get_hard_delete_user_use_case,
    get_soft_delete_user_use_case,
    get_update_user_settings_use_case,
    get_user_query_service,
)
from src.modules.users.domain.exceptions import UserNotFoundError
from src.modules.users.queries.dto import (
    UserResponseDTO,
    UserSettingsResponseDTO,
)
from src.modules.users.queries.query_service import UserQueryService

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.post(
    "/auth/login",
    response_model=TokenResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Автентифікація за логіном та паролем",
    description="Перевіряє облікові дані користувача та генерує валідний JWT access-токен.",
)
async def login(
    cmd: LoginCommand,
    use_case: Annotated[AuthenticateUserUseCase, Depends(get_authenticate_user_use_case)],
) -> TokenResponseDTO:
    """Автентифікація та отримання access-токена."""
    return await use_case.execute(cmd)


@users_router.post(
    "/telegram/sync",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_bot_internal_token)],
    summary="Синхронізація сесії Telegram-бота",
    description="Захищений сервісним токеном ендпоінт реєстрації або оновлення реквізитів Telegram.",
)
async def sync_telegram_user(
    cmd: RegisterTelegramUserCommand,
    use_case: Annotated[
        GetOrCreateTelegramUserUseCase,
        Depends(get_get_or_create_telegram_user_use_case),
    ],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserResponseDTO:
    """Синхронізація сесії користувача ботом."""
    user = await use_case.execute(cmd, commit=True)
    user_dto = await query_service.get_by_id(user.id)
    if user_dto is None:
        raise UserNotFoundError("Не вдалося завантажити синхронізованого користувача.")
    return user_dto


@users_router.get(
    "/me",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Отримання власного профілю",
    description="Повертає інформацію про поточного автентифікованого користувача.",
)
async def get_my_profile(
    current_user: CurrentUserDep,
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserResponseDTO:
    """Отримання профілю поточного користувача."""
    user_dto = await query_service.get_by_id(current_user.id)
    if user_dto is None:
        raise UserNotFoundError("Профіль користувача не знайдено.")
    return user_dto


@users_router.get(
    "/me/settings",
    response_model=UserSettingsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Отримання налаштувань користувача",
    description="Повертає параметри часового поясу, тихих годин та банківських курсів.",
)
async def get_my_settings(
    current_user: CurrentUserDep,
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserSettingsResponseDTO:
    """Отримання налаштувань поточного користувача."""
    settings_dto = await query_service.get_settings_by_user_id(current_user.id)
    if settings_dto is None:
        raise UserNotFoundError("Налаштування користувача не знайдено.")
    return settings_dto


@users_router.patch(
    "/me/settings",
    response_model=UserSettingsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Точкове оновлення налаштувань",
    description="Оновлює окремі параметри налаштувань поточного користувача з перевіркою версії (OCC).",
)
async def update_my_settings(
    cmd: UpdateUserSettingsCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[UpdateUserSettingsUseCase, Depends(get_update_user_settings_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserSettingsResponseDTO:
    """Оновлення налаштувань користувача."""
    await use_case.execute(user_id=current_user.id, cmd=cmd, commit=True)
    settings_dto = await query_service.get_settings_by_user_id(current_user.id)
    if settings_dto is None:
        raise UserNotFoundError("Налаштування користувача не знайдено.")
    return settings_dto


@users_router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалення власного облікового запису",
    description="М'яке або фізичне видалення облікового запису поточного користувача.",
)
async def delete_my_account(
    current_user: CurrentUserDep,
    soft_delete_uc: Annotated[SoftDeleteUserUseCase, Depends(get_soft_delete_user_use_case)],
    hard_delete_uc: Annotated[HardDeleteUserUseCase, Depends(get_hard_delete_user_use_case)],
    hard: Annotated[
        bool,
        Query(description="Прапорець остаточного фізичного видалення (Hard Delete)"),
    ] = False,
) -> Response:
    """Видалення облікового запису користувача."""
    if hard:
        await hard_delete_uc.execute(current_user.id, commit=True)
    else:
        await soft_delete_uc.execute(current_user.id, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@users_router.get(
    "",
    response_model=PaginatedResponse[UserResponseDTO],
    status_code=status.HTTP_200_OK,
    summary="Список користувачів системи",
    description="Адміністративний ендпоінт для отримання пагінованого переліку користувачів платформи.",
)
async def list_users(
    _admin: Annotated[CurrentUser, Depends(require_role(SystemRole.ADMIN))],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
    params: Annotated[PaginationParams, Depends()],
) -> PaginatedResponse[UserResponseDTO]:
    """Пагінований список усіх активних користувачів (тільки для адміністраторів)."""
    return await query_service.get_all(params)
