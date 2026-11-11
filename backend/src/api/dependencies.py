from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Literal, Protocol, overload
from uuid import UUID

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import current_user_id_ctx, current_username_ctx
from src.core.database import get_db_session
from src.core.domain.enums import ClientEnvironment, SystemRole
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.protocols import INotificationPublisher, IUnitOfWork
from src.core.redis import RedisClient, get_redis_client
from src.core.security import (
    CurrentUser,
    decode_token,
    verify_internal_token,
)
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications.redis_queue_publisher import RedisQueuePublisher

# Типи асинхронних резолверів користувачів
TelegramUserResolver = Callable[[int, AsyncSession], Awaitable[CurrentUser | None]]
UserResolver = Callable[[UUID, AsyncSession], Awaitable[CurrentUser | None]]

_telegram_user_resolver: TelegramUserResolver | None = None
_user_resolver: UserResolver | None = None
_oauth2_scheme = HTTPBearer(auto_error=False)


def register_telegram_user_resolver(resolver: TelegramUserResolver) -> None:
    """
    Реєстрація резолвера Telegram-користувача.

    Використовується модулем users для підключення механізму пошуку користувача
    за Telegram ID без виникнення циклічних міжмодульних імпортів.
    """
    global _telegram_user_resolver
    _telegram_user_resolver = resolver


def register_user_resolver(resolver: UserResolver) -> None:
    """
    Реєстрація резолвера користувача за UUID.

    Використовується модулем users для перевірки статусу активності користувача в БД
    та блокування доступу деактивованим користувачам без циклічних міжмодульних імпортів.
    """
    global _user_resolver
    _user_resolver = resolver


def get_uow(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IUnitOfWork:
    """Фабрика Unit of Work для поточної сесії запиту (Request Scope)."""
    return SqlAlchemyUnitOfWork(session=session)


def get_notification_publisher(
    redis: Annotated[RedisClient, Depends(get_redis_client)],
) -> INotificationPublisher:
    """Фабрика видавця сповіщень у чергу Redis."""
    return RedisQueuePublisher(redis_client=redis)


def verify_bot_internal_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    """
    Перевірка внутрішнього сервісного токена запитів від Telegram-бота.

    Викидає UnauthorizedException у разі відсутності або недійсності токена.
    """
    if not x_internal_token or not verify_internal_token(x_internal_token):
        raise UnauthorizedException("Недійсний або відсутній внутрішній сервісний токен.")


def detect_client_environment(
    authorization: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = None,
    x_internal_token: str | None = None,
) -> ClientEnvironment:
    """
    Визначає середовище клієнта:
    - Якщо передано X-Internal-Token -> TELEGRAM_BOT (перед цим токен валідується).
    - В іншому випадку -> WEB_API.
    """
    if x_internal_token is not None:
        if not verify_internal_token(x_internal_token):
            raise UnauthorizedException("Недійсний внутрішній сервісний токен.")
        return ClientEnvironment.TELEGRAM_BOT
    return ClientEnvironment.WEB_API


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_oauth2_scheme)] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    x_telegram_id: Annotated[int | None, Header(alias="X-Telegram-Id")] = None,
    x_user_id: Annotated[UUID | None, Header(alias="X-User-Id")] = None,
) -> CurrentUser:
    """
    Комбінована Stateless автентифікація поточного користувача.

    Підтримує два взаємодоповнюючі режими:
    1. Internal Service Header (для Telegram-бота):
       - Вимагає валідного `X-Internal-Token`.
       - При наявності `_telegram_user_resolver` та `X-Telegram-Id` шукає користувача в БД.
       - При прямому передаванні `X-User-Id` (або в тестових середовищах) формує об'єкт користувача.
       - Встановлює environment=ClientEnvironment.TELEGRAM_BOT.
    2. Bearer JWT (для Web API та адмін-панелі):
       - Декодує та валідує токен із заголовка `Authorization: Bearer <token>`.
       - Перевіряє термін придатності, клейми користувача та системну роль.
       - Встановлює environment=ClientEnvironment.WEB_API.
    """
    # 1. Режим внутрішнього сервісного токена (Telegram Bot / Мікросервіси)
    if x_internal_token is not None:
        if not verify_internal_token(x_internal_token):
            raise UnauthorizedException("Недійсний внутрішній сервісний токен.")

        if _telegram_user_resolver is not None and x_telegram_id is not None:
            resolved_user = await _telegram_user_resolver(x_telegram_id, session)
            if resolved_user is not None:
                user = resolved_user.model_copy(update={"environment": ClientEnvironment.TELEGRAM_BOT})
                current_user_id_ctx.set(user.id)
                current_username_ctx.set(user.username)
                return user

        if x_user_id is not None:
            user = CurrentUser(
                id=x_user_id,
                username=f"tg_{x_telegram_id or x_user_id}",
                role=SystemRole.USER,
                telegram_id=x_telegram_id,
                environment=ClientEnvironment.TELEGRAM_BOT,
            )
            current_user_id_ctx.set(user.id)
            current_username_ctx.set(user.username)
            return user

        raise UnauthorizedException("Користувача з вказаним Telegram ID не знайдено або не передано X-Telegram-Id.")

    # 2. Режим Bearer JWT токена
    raw_token: str | None = None
    if credentials is not None and credentials.credentials:
        raw_token = credentials.credentials
    elif authorization is not None:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_token = parts[1]
        elif len(parts) == 1:
            raw_token = parts[0]

    if raw_token is not None:
        try:
            payload = decode_token(raw_token)
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedException("Термін дії токена закінчився.") from exc
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedException("Недійсний токен автентифікації.") from exc

        sub = payload.get("sub")
        if not sub:
            raise UnauthorizedException("Недійсний формат токена (відсутній sub).")

        try:
            user_id = UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise UnauthorizedException("Недійсний ідентифікатор користувача в токені.") from exc

        # Верифікація статусу користувача в БД (деактивовані користувачі блокуються)
        if _user_resolver is not None:
            resolved_user = await _user_resolver(user_id, session)
            if resolved_user is not None:
                user = resolved_user.model_copy(update={"environment": ClientEnvironment.WEB_API})
                current_user_id_ctx.set(user.id)
                current_username_ctx.set(user.username)
                return user

        username = str(payload.get("username") or f"user_{user_id}")
        raw_role = payload.get("role", SystemRole.USER.value)
        try:
            role = SystemRole(raw_role)
        except ValueError:
            role = SystemRole.USER

        telegram_id_raw = payload.get("telegram_id")
        telegram_id: int | None = None
        if telegram_id_raw is not None:
            try:
                telegram_id = int(telegram_id_raw)
            except (ValueError, TypeError):
                telegram_id = None

        jwt_user = CurrentUser(
            id=user_id,
            username=username,
            role=role,
            telegram_id=telegram_id,
            environment=ClientEnvironment.WEB_API,
        )
        current_user_id_ctx.set(jwt_user.id)
        current_username_ctx.set(jwt_user.username)
        return jwt_user

    raise UnauthorizedException("Необхідна автентифікація (Bearer JWT або X-Internal-Token).")


@overload
def authorize(
    environments: Sequence[ClientEnvironment] = ...,
    roles: Sequence[SystemRole] | None = ...,
    require_auth: Literal[True] = True,
) -> Callable[..., Awaitable[CurrentUser]]: ...


@overload
def authorize(
    environments: Sequence[ClientEnvironment] = ...,
    roles: Sequence[SystemRole] | None = ...,
    require_auth: Literal[False] = False,
) -> Callable[..., Awaitable[None]]: ...


def authorize(
    environments: Sequence[ClientEnvironment] = (
        ClientEnvironment.WEB_API,
        ClientEnvironment.TELEGRAM_BOT,
    ),
    roles: Sequence[SystemRole] | None = None,
    require_auth: bool = True,
) -> Callable[..., Awaitable[CurrentUser | None]]:
    """
    Фабрика багаторівневої авторизації та контролю доступу:
    1. Перевірка середовища виклику (ClientEnvironment):
       - TELEGRAM_BOT: вимагає валідного X-Internal-Token.
       - WEB_API: запити без X-Internal-Token (Bearer JWT або відкриті).
       - У разі виклику ендпоінта з недозволеного середовища -> 403 Forbidden.
    2. Перевірка автентифікації користувача (якщо require_auth=True):
       - Виконує резолв користувача для відповідного середовища.
       - У разі відсутності креденшелів -> 401 Unauthorized.
    3. Перевірка системної ролі користувача (RBAC, якщо передано roles):
       - SuperAdmin завжди має повний доступ.
       - Для інших користувачів роль має бути в roles, інакше -> 403 Forbidden.
    """

    async def _authorizer(
        session: Annotated[AsyncSession, Depends(get_db_session)],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_oauth2_scheme)] = None,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
        x_telegram_id: Annotated[int | None, Header(alias="X-Telegram-Id")] = None,
        x_user_id: Annotated[UUID | None, Header(alias="X-User-Id")] = None,
    ) -> CurrentUser | None:
        has_internal_token = x_internal_token is not None
        has_bearer_token = (credentials is not None and bool(credentials.credentials)) or (authorization is not None)

        if has_internal_token:
            if not verify_internal_token(x_internal_token):  # type: ignore[arg-type]
                raise UnauthorizedException("Недійсний внутрішній сервісний токен.")
            detected_env = ClientEnvironment.TELEGRAM_BOT
        elif has_bearer_token:
            detected_env = ClientEnvironment.WEB_API
        else:
            # Якщо ендпоінт вимагає виключно Telegram-бота, але токен не передано
            if ClientEnvironment.TELEGRAM_BOT in environments and ClientEnvironment.WEB_API not in environments:
                raise UnauthorizedException("Необхідна автентифікація: відсутній внутрішній сервісний токен.")
            detected_env = ClientEnvironment.WEB_API

        # 1. Перевірка дозволених середовищ (Environment Check)
        if detected_env not in environments:
            raise ForbiddenException(f"Доступ із середовища '{detected_env.value}' до цього ендпоінта заборонено.")

        # 2. Перевірка автентифікації користувача (Authentication Check)
        if not require_auth:
            return None

        current_user = await get_current_user(
            session=session,
            credentials=credentials,
            authorization=authorization,
            x_internal_token=x_internal_token,
            x_telegram_id=x_telegram_id,
            x_user_id=x_user_id,
        )

        # 3. Перевірка системної ролі (Role Check / RBAC)
        if roles is not None and not (current_user.is_super_admin or current_user.role in roles):
            raise ForbiddenException("Недостатньо прав для виконання цієї дії.")

        return current_user

    return _authorizer


class RoleChecker(Protocol):
    """Протокол залежності перевірки прав доступу (RBAC) за ролями."""

    async def __call__(
        self,
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser: ...


def require_role(
    *allowed_roles: SystemRole,
    environments: Sequence[ClientEnvironment] = (
        ClientEnvironment.WEB_API,
        ClientEnvironment.TELEGRAM_BOT,
    ),
) -> RoleChecker:
    """
    Фабрика перевірки прав доступу (RBAC) за ролями та середовищами.

    Користувач із роллю SUPER_ADMIN завжди має доступ.
    Для інших користувачів їхня роль має входити до списку `allowed_roles`.
    """

    async def _role_checker(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.environment not in environments:
            raise ForbiddenException(
                f"Доступ із середовища '{current_user.environment.value}' до цього ендпоінта заборонено."
            )
        if current_user.is_super_admin or current_user.role in allowed_roles:
            return current_user
        raise ForbiddenException("Недостатньо прав для виконання цієї дії.")

    return _role_checker


# Базові системні залежності
UoWDep = Annotated[IUnitOfWork, Depends(get_uow)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
PublisherDep = Annotated[INotificationPublisher, Depends(get_notification_publisher)]

# Користувач із будь-якого дозволеного середовища (Web API або Telegram Bot)
CurrentUserDep = Annotated[
    CurrentUser,
    Depends(
        authorize(
            environments=(ClientEnvironment.WEB_API, ClientEnvironment.TELEGRAM_BOT),
            require_auth=True,
        )
    ),
]

# Користувач виключно з веб-інтерфейсу (Web API)
WebUserDep = Annotated[
    CurrentUser,
    Depends(
        authorize(
            environments=(ClientEnvironment.WEB_API,),
            require_auth=True,
        )
    ),
]

# Користувач виключно з Telegram-бота
BotUserDep = Annotated[
    CurrentUser,
    Depends(
        authorize(
            environments=(ClientEnvironment.TELEGRAM_BOT,),
            require_auth=True,
        )
    ),
]

# Адміністратор (Admin або SuperAdmin) виключно з Web API
AdminWebDep = Annotated[
    CurrentUser,
    Depends(
        authorize(
            environments=(ClientEnvironment.WEB_API,),
            roles=(SystemRole.ADMIN, SystemRole.SUPER_ADMIN),
            require_auth=True,
        )
    ),
]

# Суперадміністратор виключно з Web API
SuperAdminWebDep = Annotated[
    CurrentUser,
    Depends(
        authorize(
            environments=(ClientEnvironment.WEB_API,),
            roles=(SystemRole.SUPER_ADMIN,),
            require_auth=True,
        )
    ),
]
