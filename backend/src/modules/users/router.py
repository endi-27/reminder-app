from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from src.api.dependencies import (
    AdminWebDep,
    CurrentUserDep,
    SuperAdminWebDep,
    WebUserDep,
    authorize,
)
from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.core import limiter, settings
from src.core.domain.enums import ClientEnvironment
from src.modules.users.application.dto import (
    ChangeMyPasswordCommand,
    ChangePasswordAdminCommand,
    CreateTelegramAccountAdminCommand,
    CreateUserCommand,
    LinkTelegramAccountCommand,
    LoginCommand,
    RegisterTelegramUserCommand,
    TokenResponseDTO,
    UpdateMyTelegramAccountCommand,
    UpdateMyUsernameCommand,
    UpdateTelegramAccountAdminCommand,
    UpdateUserProfileAdminCommand,
    UpdateUserSettingsCommand,
)
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
from src.modules.users.dependencies import (
    get_authenticate_user_use_case,
    get_change_my_password_use_case,
    get_change_password_admin_use_case,
    get_create_telegram_account_admin_use_case,
    get_create_user_use_case,
    get_get_or_create_telegram_user_use_case,
    get_hard_delete_telegram_account_use_case,
    get_hard_delete_user_use_case,
    get_link_telegram_account_use_case,
    get_reset_user_settings_use_case,
    get_restore_user_use_case,
    get_soft_delete_user_use_case,
    get_unlink_telegram_account_use_case,
    get_update_my_telegram_account_use_case,
    get_update_my_username_use_case,
    get_update_other_user_settings_use_case,
    get_update_telegram_account_admin_use_case,
    get_update_user_profile_admin_use_case,
    get_update_user_settings_use_case,
    get_user_query_service,
)
from src.modules.users.domain.exceptions import (
    TelegramAccountNotFoundError,
    UserNotFoundError,
)
from src.modules.users.queries.dto import (
    TelegramAccountDetailDTO,
    UserResponseDTO,
    UserSettingsResponseDTO,
)
from src.modules.users.queries.query_service import UserQueryService

users_router = APIRouter(prefix="/users", tags=["Users"])


# --- 1. Автентифікація ---
@users_router.post(
    "/auth/login",
    response_model=TokenResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Автентифікація за логіном та паролем (Сценарій 1)",
    description="Перевіряє облікові дані користувача та генерує валідний JWT access-токен.",
)
@limiter.limit(settings.rate_limit.auth_login_limit)
async def login(
    request: Request,
    cmd: LoginCommand,
    use_case: Annotated[AuthenticateUserUseCase, Depends(get_authenticate_user_use_case)],
) -> TokenResponseDTO:
    """Автентифікація та отримання access-токена."""
    return await use_case.execute(cmd)


# --- 2. Створення нового користувача через Web API ---
@users_router.post(
    "",
    response_model=UserResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Створення нового користувача (Сценарій 2)",
    description="Адміністративний ендпоінт створення нового користувача з налаштуваннями.",
)
@limiter.limit(settings.rate_limit.user_create_limit)
async def create_user(
    request: Request,
    cmd: CreateUserCommand,
    creator: AdminWebDep,
    use_case: Annotated[CreateUserUseCase, Depends(get_create_user_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserResponseDTO:
    """Створення облікового запису користувача."""
    user_id = await use_case.execute(creator=creator, cmd=cmd, commit=True)
    user_dto = await query_service.get_by_id(user_id)
    if user_dto is None:
        raise UserNotFoundError("Не вдалося завантажити створеного користувача.")
    return user_dto


# --- 3. Telegram Get or Create (/start) ---
@users_router.post(
    "/telegram/sync",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(authorize(environments=[ClientEnvironment.TELEGRAM_BOT], require_auth=False))],
    summary="Синхронізація сесії Telegram-бота (Сценарій 3)",
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
    user_id = await use_case.execute(cmd, commit=True)
    user_dto = await query_service.get_by_id(user_id)
    if user_dto is None:
        raise UserNotFoundError("Не вдалося завантажити синхронізованого користувача.")
    return user_dto


# --- 4. Прив'язати Telegram до User ---
@users_router.post(
    "/{user_id}/telegram/link",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Прив'язка Telegram-акаунта до користувача (Сценарій 4)",
)
async def link_telegram_account(
    user_id: UUID,
    cmd: LinkTelegramAccountCommand,
    _admin: AdminWebDep,
    use_case: Annotated[LinkTelegramAccountUseCase, Depends(get_link_telegram_account_use_case)],
) -> Response:
    """Прив'язка вільного Telegram-профілю до користувача (Admin/SuperAdmin)."""
    await use_case.execute(user_id=user_id, cmd=cmd, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 5. Відв'язати Telegram від User ---
@users_router.post(
    "/{user_id}/telegram/unlink",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Відв'язування Telegram-акаунта від користувача (Сценарій 5)",
)
async def unlink_telegram_account(
    user_id: UUID,
    _admin: AdminWebDep,
    use_case: Annotated[UnlinkTelegramAccountUseCase, Depends(get_unlink_telegram_account_use_case)],
) -> Response:
    """Відв'язування Telegram-профілю від користувача (Admin/SuperAdmin)."""
    await use_case.execute(user_id=user_id, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 6. Зміна пароля комусь ---
@users_router.post(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Зміна пароля іншому користувачу (Сценарій 6)",
)
@limiter.limit(settings.rate_limit.password_admin_limit)
async def change_password_admin(
    request: Request,
    user_id: UUID,
    cmd: ChangePasswordAdminCommand,
    actor: SuperAdminWebDep,
    use_case: Annotated[ChangePasswordAdminUseCase, Depends(get_change_password_admin_use_case)],
) -> Response:
    """Встановлення або зміна пароля користувача (тільки SuperAdmin)."""
    await use_case.execute(actor=actor, target_user_id=user_id, cmd=cmd, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 7. Зміна пароля собі ---
@users_router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Зміна власного пароля (Сценарій 7)",
)
@limiter.limit(settings.rate_limit.password_change_limit)
async def change_my_password(
    request: Request,
    cmd: ChangeMyPasswordCommand,
    current_user: WebUserDep,
    use_case: Annotated[ChangeMyPasswordUseCase, Depends(get_change_my_password_use_case)],
) -> Response:
    """Зміна власного пароля користувачем з обов'язковим поточним паролем."""
    await use_case.execute(user_id=current_user.id, cmd=cmd, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 8. Зміна даних у таблиці Users комусь ---
@users_router.patch(
    "/{user_id}",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Оновлення профілю іншого користувача (Сценарій 8)",
)
async def update_user_profile_admin(
    user_id: UUID,
    cmd: UpdateUserProfileAdminCommand,
    actor: SuperAdminWebDep,
    use_case: Annotated[UpdateUserProfileAdminUseCase, Depends(get_update_user_profile_admin_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserResponseDTO:
    """Оновлення імені та ролі іншого користувача (тільки SuperAdmin)."""
    await use_case.execute(actor=actor, target_user_id=user_id, cmd=cmd, commit=True)
    user_dto = await query_service.get_by_id(user_id)
    if user_dto is None:
        raise UserNotFoundError("Не вдалося завантажити оновленого користувача.")
    return user_dto


# --- 9. Зміна username собі ---
@users_router.patch(
    "/me/username",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Оновлення власного логіна (Сценарій 9)",
)
async def update_my_username(
    cmd: UpdateMyUsernameCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[UpdateMyUsernameUseCase, Depends(get_update_my_username_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserResponseDTO:
    """Оновлення імені поточного користувача."""
    await use_case.execute(user_id=current_user.id, cmd=cmd, commit=True)
    user_dto = await query_service.get_by_id(current_user.id)
    if user_dto is None:
        raise UserNotFoundError("Не вдалося завантажити оновленого користувача.")
    return user_dto


# --- Створення нового Telegram-акаунта (тільки SuperAdmin) ---
@users_router.post(
    "/telegram-accounts",
    response_model=TelegramAccountDetailDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Створення нового запису Telegram-акаунта (тільки SuperAdmin)",
    description=(
        "Створює новий запис у таблиці user_telegram_accounts з точним вказанням telegram_id та telegram_chat_id."
    ),
)
async def create_telegram_account_admin(
    cmd: CreateTelegramAccountAdminCommand,
    actor: SuperAdminWebDep,
    use_case: Annotated[
        CreateTelegramAccountAdminUseCase,
        Depends(get_create_telegram_account_admin_use_case),
    ],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> TelegramAccountDetailDTO:
    """Створення запису Telegram-акаунта (тільки SuperAdmin)."""
    account_id = await use_case.execute(actor=actor, cmd=cmd, commit=True)
    dto = await query_service.get_telegram_account_by_id(account_id)
    if dto is None:
        raise TelegramAccountNotFoundError("Не вдалося завантажити створений Telegram-профіль.")
    return dto


# --- 10. Зміна даних таблиці Telegram_users комусь ---
@users_router.patch(
    "/telegram-accounts/{account_id}",
    response_model=TelegramAccountDetailDTO,
    status_code=status.HTTP_200_OK,
    summary="Оновлення даних Telegram-акаунта адміністратором (Сценарій 10)",
)
async def update_telegram_account_admin(
    account_id: UUID,
    cmd: UpdateTelegramAccountAdminCommand,
    actor: SuperAdminWebDep,
    use_case: Annotated[
        UpdateTelegramAccountAdminUseCase,
        Depends(get_update_telegram_account_admin_use_case),
    ],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> TelegramAccountDetailDTO:
    """Зміна реквізитів Telegram-профілю (тільки SuperAdmin)."""
    await use_case.execute(actor=actor, account_id=account_id, cmd=cmd, commit=True)
    dto = await query_service.get_telegram_account_by_id(account_id)
    if dto is None:
        raise UserNotFoundError("Telegram-профіль не знайдено.")
    return dto


# --- 11. Зміна даних таблиці Telegram_users собі ---
@users_router.patch(
    "/me/telegram",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Оновлення візуальних даних свого Telegram-профілю (Сценарій 11)",
)
async def update_my_telegram_account(
    cmd: UpdateMyTelegramAccountCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[UpdateMyTelegramAccountUseCase, Depends(get_update_my_telegram_account_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserResponseDTO:
    """Оновлення візуальних реквізитів власного профілю Telegram."""
    await use_case.execute(user_id=current_user.id, cmd=cmd, commit=True)
    user_dto = await query_service.get_by_id(current_user.id)
    if user_dto is None:
        raise UserNotFoundError("Не вдалося завантажити оновленого користувача.")
    return user_dto


# --- 12. Зміна налаштувань комусь ---
@users_router.patch(
    "/{user_id}/settings",
    response_model=UserSettingsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Оновлення налаштувань іншого користувача (Сценарій 12)",
)
async def update_other_user_settings(
    user_id: UUID,
    cmd: UpdateUserSettingsCommand,
    actor: AdminWebDep,
    use_case: Annotated[UpdateOtherUserSettingsUseCase, Depends(get_update_other_user_settings_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserSettingsResponseDTO:
    """Зміна налаштувань іншому користувачу (Admin/SuperAdmin)."""
    await use_case.execute(actor=actor, target_user_id=user_id, cmd=cmd, commit=True)
    settings_dto = await query_service.get_settings_by_user_id(user_id)
    if settings_dto is None:
        raise UserNotFoundError("Налаштування користувача не знайдено.")
    return settings_dto


# --- 13. Зміна налаштувань собі ---
@users_router.patch(
    "/me/settings",
    response_model=UserSettingsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Оновлення власних налаштувань (Сценарій 13)",
)
async def update_my_settings(
    cmd: UpdateUserSettingsCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[UpdateUserSettingsUseCase, Depends(get_update_user_settings_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserSettingsResponseDTO:
    """Оновлення налаштувань поточного користувача з контролем версій (OCC)."""
    await use_case.execute(user_id=current_user.id, cmd=cmd, commit=True)
    settings_dto = await query_service.get_settings_by_user_id(current_user.id)
    if settings_dto is None:
        raise UserNotFoundError("Налаштування користувача не знайдено.")
    return settings_dto


# --- 14. Скидання налаштувань собі ---
@users_router.post(
    "/me/settings/reset",
    response_model=UserSettingsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Скидання власних налаштувань до дефолтних (Сценарій 14)",
)
async def reset_my_settings(
    current_user: CurrentUserDep,
    use_case: Annotated[ResetUserSettingsUseCase, Depends(get_reset_user_settings_use_case)],
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserSettingsResponseDTO:
    """Скидання налаштувань поточного користувача до значень за замовчуванням."""
    await use_case.execute(user_id=current_user.id, commit=True)
    settings_dto = await query_service.get_settings_by_user_id(current_user.id)
    if settings_dto is None:
        raise UserNotFoundError("Налаштування користувача не знайдено.")
    return settings_dto


# --- 15. Soft Delete користувача ---
@users_router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="М'яке видалення користувача (Сценарій 15)",
)
async def soft_delete_user(
    user_id: UUID,
    actor: AdminWebDep,
    use_case: Annotated[SoftDeleteUserUseCase, Depends(get_soft_delete_user_use_case)],
) -> Response:
    """М'яка деактивація користувача (Admin/SuperAdmin)."""
    await use_case.execute(actor=actor, target_user_id=user_id, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 16. Відновлення користувача ---
@users_router.post(
    "/{user_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Відновлення деактивованого користувача (Сценарій 16)",
)
async def restore_user(
    user_id: UUID,
    _admin: AdminWebDep,
    use_case: Annotated[RestoreUserUseCase, Depends(get_restore_user_use_case)],
) -> Response:
    """Відновлення м'яко видаленого користувача (Admin/SuperAdmin)."""
    await use_case.execute(target_user_id=user_id, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 17. Hard Delete користувача ---
@users_router.delete(
    "/{user_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Остаточне фізичне видалення користувача (Сценарій 17)",
)
@limiter.limit("10/minute")
async def hard_delete_user(
    request: Request,
    user_id: UUID,
    actor: SuperAdminWebDep,
    use_case: Annotated[HardDeleteUserUseCase, Depends(get_hard_delete_user_use_case)],
) -> Response:
    """Фізичне видалення користувача з бази даних (тільки SuperAdmin)."""
    await use_case.execute(actor=actor, target_user_id=user_id, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 18. Hard Delete Telegram-акаунта ---
@users_router.delete(
    "/telegram-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Остаточне фізичне видалення Telegram-профілю (Сценарій 18)",
)
async def hard_delete_telegram_account(
    account_id: UUID,
    _super_admin: SuperAdminWebDep,
    use_case: Annotated[
        HardDeleteTelegramAccountUseCase,
        Depends(get_hard_delete_telegram_account_use_case),
    ],
) -> Response:
    """Фізичне видалення Telegram-акаунта за умови, що він не прив'язаний (тільки SuperAdmin)."""
    await use_case.execute(account_id=account_id, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Перегляд профілів (Read Endpoints) ---
@users_router.get(
    "/me",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Отримання власного профілю",
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
    summary="Отримання налаштувань поточного користувача",
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


@users_router.get(
    "/telegram-accounts",
    response_model=list[TelegramAccountDetailDTO],
    status_code=status.HTTP_200_OK,
    summary="Перелік усіх Telegram-профілів (тільки для адміністраторів)",
)
async def list_telegram_accounts(
    _admin: AdminWebDep,
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> list[TelegramAccountDetailDTO]:
    """Список усіх Telegram-акаунтів платформи."""
    return await query_service.get_all_telegram_accounts()


@users_router.get(
    "/{user_id}",
    response_model=UserResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Отримання профілю користувача за ID (тільки для адміністраторів)",
)
async def get_user_by_id(
    user_id: UUID,
    _admin: AdminWebDep,
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserResponseDTO:
    """Отримання профілю за ID."""
    user_dto = await query_service.get_by_id(user_id)
    if user_dto is None:
        raise UserNotFoundError(f"Користувача з ID {user_id} не знайдено.")
    return user_dto


@users_router.get(
    "",
    response_model=PaginatedResponse[UserResponseDTO],
    status_code=status.HTTP_200_OK,
    summary="Список користувачів системи",
)
async def list_users(
    _admin: AdminWebDep,
    query_service: Annotated[UserQueryService, Depends(get_user_query_service)],
    params: Annotated[PaginationParams, Depends()],
) -> PaginatedResponse[UserResponseDTO]:
    """Пагінований список усіх активних користувачів (тільки для адміністраторів)."""
    return await query_service.get_all(params)
