from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, Depends, FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from src.api.dependencies import (
    AdminWebDep,
    BotUserDep,
    CurrentUserDep,
    SuperAdminWebDep,
    WebUserDep,
    authorize,
    detect_client_environment,
)
from src.api.exception_handlers import setup_exception_handlers
from src.core.config import settings
from src.core.database import get_db_session
from src.core.domain.enums import ClientEnvironment, SystemRole
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.security import create_access_token


@pytest.fixture(autouse=True)
def cleanup_resolvers() -> Iterator[None]:
    """Очищення глобальних резолверів після кожного тесту."""
    yield
    from src.api import dependencies

    dependencies._telegram_user_resolver = None
    dependencies._user_resolver = None


class TestDetectClientEnvironment:
    """Тестування функції детекції середовища клієнта."""

    def test_detect_internal_token_valid(self) -> None:
        """Перевірка детекції середовища Telegram-бота за валідним внутрішнім токеном."""
        env = detect_client_environment(x_internal_token=settings.auth.internal_token)
        assert env == ClientEnvironment.TELEGRAM_BOT

    def test_detect_internal_token_invalid(self) -> None:
        """Перевірка викидання 401 Unauthorized при недійсному внутрішньому токені."""
        with pytest.raises(UnauthorizedException) as exc_info:
            detect_client_environment(x_internal_token="invalid_secret_token")
        assert "Недійсний внутрішній сервісний токен." in exc_info.value.message

    def test_detect_web_api_when_no_internal_token(self) -> None:
        """Перевірка детекції середовища Web API за замовчуванням при відсутності X-Internal-Token."""
        env = detect_client_environment(authorization="Bearer some_token")
        assert env == ClientEnvironment.WEB_API

        env_none = detect_client_environment()
        assert env_none == ClientEnvironment.WEB_API


class TestAuthorizeUnitScenarios:
    """Юніт-тести фабрики authorize для різних комбінацій середовищ та ролей."""

    @pytest.mark.asyncio
    async def test_bot_calling_web_only_endpoint_forbidden(self) -> None:
        """Запит від бота на ендпоінт тільки для Web API блокується з 403 Forbidden."""
        auth_fn = authorize(environments=(ClientEnvironment.WEB_API,))
        session = AsyncMock(spec=AsyncSession)

        with pytest.raises(ForbiddenException) as exc_info:
            await auth_fn(
                session=session,
                x_internal_token=settings.auth.internal_token,
                x_telegram_id=123456,
            )
        assert "TELEGRAM_BOT" in exc_info.value.message
        assert "заборонено" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_web_bearer_calling_bot_only_endpoint_forbidden(self) -> None:
        """Запит з Bearer токеном на ендпоінт тільки для Telegram-бота блокується з 403 Forbidden."""
        auth_fn = authorize(environments=(ClientEnvironment.TELEGRAM_BOT,))
        session = AsyncMock(spec=AsyncSession)
        token = create_access_token({"sub": str(uuid7()), "role": "USER"})

        with pytest.raises(ForbiddenException) as exc_info:
            await auth_fn(
                session=session,
                authorization=f"Bearer {token}",
            )
        assert "WEB_API" in exc_info.value.message
        assert "заборонено" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_bot_only_unauthenticated_without_token_raises_401(self) -> None:
        """Запит без жодних токенів до Bot-only ендпоінта викидає 401 Unauthorized."""
        auth_fn = authorize(environments=(ClientEnvironment.TELEGRAM_BOT,), require_auth=False)
        session = AsyncMock(spec=AsyncSession)

        with pytest.raises(UnauthorizedException) as exc_info:
            await auth_fn(session=session)
        assert "відсутній внутрішній сервісний токен" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_bot_only_with_valid_token_require_auth_false_succeeds(self) -> None:
        """Запит від бота до Bot-only ендпоінта без вимоги користувача (require_auth=False) повертає None."""
        auth_fn = authorize(environments=(ClientEnvironment.TELEGRAM_BOT,), require_auth=False)
        session = AsyncMock(spec=AsyncSession)

        # Успішне проходження без винятків
        await auth_fn(
            session=session,
            x_internal_token=settings.auth.internal_token,
        )

    @pytest.mark.asyncio
    async def test_web_admin_route_insufficient_role_forbidden(self) -> None:
        """Web-користувач зі звичайною роллю USER не має доступу до адмін-ендпоінта (403 Forbidden)."""
        auth_fn = authorize(
            environments=(ClientEnvironment.WEB_API,),
            roles=(SystemRole.ADMIN, SystemRole.SUPER_ADMIN),
            require_auth=True,
        )
        session = AsyncMock(spec=AsyncSession)
        user_id = uuid7()
        token = create_access_token({"sub": str(user_id), "role": "USER", "username": "user1"})

        with pytest.raises(ForbiddenException) as exc_info:
            await auth_fn(
                session=session,
                authorization=f"Bearer {token}",
            )
        assert "Недостатньо прав для виконання цієї дії." in exc_info.value.message

    @pytest.mark.asyncio
    async def test_web_admin_route_admin_role_succeeds(self) -> None:
        """Web-користувач із роллю ADMIN успішно проходить авторизацію."""
        auth_fn = authorize(
            environments=(ClientEnvironment.WEB_API,),
            roles=(SystemRole.ADMIN, SystemRole.SUPER_ADMIN),
            require_auth=True,
        )
        session = AsyncMock(spec=AsyncSession)
        user_id = uuid7()
        token = create_access_token({"sub": str(user_id), "role": "ADMIN", "username": "admin1"})

        user = await auth_fn(
            session=session,
            authorization=f"Bearer {token}",
        )
        assert user is not None
        assert user.id == user_id
        assert user.role == SystemRole.ADMIN
        assert user.environment == ClientEnvironment.WEB_API

    @pytest.mark.asyncio
    async def test_super_admin_bypasses_specific_roles(self) -> None:
        """SUPER_ADMIN успішно проходить навіть якщо roles вказує лише ADMIN."""
        auth_fn = authorize(
            environments=(ClientEnvironment.WEB_API,),
            roles=(SystemRole.ADMIN,),
            require_auth=True,
        )
        session = AsyncMock(spec=AsyncSession)
        user_id = uuid7()
        token = create_access_token({"sub": str(user_id), "role": "SUPER_ADMIN", "username": "root"})

        user = await auth_fn(
            session=session,
            authorization=f"Bearer {token}",
        )
        assert user is not None
        assert user.role == SystemRole.SUPER_ADMIN
        assert user.environment == ClientEnvironment.WEB_API


class TestFastApiIntegrationWithTypedDependencies:
    """Тестування HTTP-запитів через FastAPI застосунок з типізованими аліасами залежностей."""

    @pytest.fixture
    def test_app(self) -> FastAPI:
        """Створення тестового FastAPI застосунку з маршрутами різних типів доступу."""
        app = FastAPI()
        setup_exception_handlers(app)
        router = APIRouter()

        @router.get("/admin-only")
        async def admin_route(admin: AdminWebDep) -> dict[str, str]:
            return {"user": admin.username, "role": admin.role.value, "env": admin.environment.value}

        @router.get("/super-admin-only")
        async def super_admin_route(super_admin: SuperAdminWebDep) -> dict[str, str]:
            return {"user": super_admin.username, "env": super_admin.environment.value}

        @router.get("/web-user")
        async def web_user_route(user: WebUserDep) -> dict[str, str]:
            return {"user": user.username, "env": user.environment.value}

        @router.get("/bot-user")
        async def bot_user_route(bot_user: BotUserDep) -> dict[str, str]:
            return {"user": bot_user.username, "env": bot_user.environment.value}

        @router.get("/shared-any")
        async def shared_route(user: CurrentUserDep) -> dict[str, str]:
            return {"user": user.username, "env": user.environment.value}

        @router.post(
            "/bot-sync",
            dependencies=[Depends(authorize(environments=[ClientEnvironment.TELEGRAM_BOT], require_auth=False))],
        )
        async def bot_sync_route() -> dict[str, str]:
            return {"status": "synced"}

        app.include_router(router)

        # Mock get_db_session
        async def _mock_get_db() -> AsyncMock:
            return AsyncMock(spec=AsyncSession)

        app.dependency_overrides[get_db_session] = _mock_get_db
        return app

    @pytest.mark.asyncio
    async def test_admin_web_dep_allows_admin_jwt(self, test_app: FastAPI) -> None:
        """AdminWebDep дозволяє запит із валідним ADMIN JWT."""
        user_id = uuid7()
        token = create_access_token({"sub": str(user_id), "role": "ADMIN", "username": "admin_test"})

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get("/admin-only")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["user"] == "admin_test"
            assert data["env"] == "WEB_API"

    @pytest.mark.asyncio
    async def test_admin_web_dep_rejects_bot_token(self, test_app: FastAPI) -> None:
        """AdminWebDep відхиляє запит від Telegram-бота (403 Forbidden)."""
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={
                "X-Internal-Token": settings.auth.internal_token,
                "X-User-Id": str(uuid7()),
            },
        ) as client:
            resp = await client.get("/admin-only")
            assert resp.status_code == status.HTTP_403_FORBIDDEN
            assert "TELEGRAM_BOT" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_super_admin_dep_rejects_admin(self, test_app: FastAPI) -> None:
        """SuperAdminWebDep відхиляє звичайного ADMIN (403 Forbidden)."""
        token = create_access_token({"sub": str(uuid7()), "role": "ADMIN", "username": "just_admin"})

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get("/super-admin-only")
            assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_super_admin_dep_allows_super_admin(self, test_app: FastAPI) -> None:
        """SuperAdminWebDep дозволяє SUPER_ADMIN."""
        token = create_access_token({"sub": str(uuid7()), "role": "SUPER_ADMIN", "username": "big_boss"})

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get("/super-admin-only")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["user"] == "big_boss"

    @pytest.mark.asyncio
    async def test_bot_sync_allows_bot_token(self, test_app: FastAPI) -> None:
        """Bot sync маршрут успішно виконується з валідним X-Internal-Token."""
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={"X-Internal-Token": settings.auth.internal_token},
        ) as client:
            resp = await client.post("/bot-sync")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["status"] == "synced"

    @pytest.mark.asyncio
    async def test_bot_sync_rejects_web_bearer(self, test_app: FastAPI) -> None:
        """Bot sync маршрут блокує Bearer токен (403 Forbidden)."""
        token = create_access_token({"sub": str(uuid7()), "role": "USER"})

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.post("/bot-sync")
            assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_shared_route_allows_both_web_and_bot(self, test_app: FastAPI) -> None:
        """CurrentUserDep дозволяє як Web API користувачів, так і користувачів Telegram-бота."""
        # 1. Через Web API
        token = create_access_token({"sub": str(uuid7()), "username": "web_guy"})
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get("/shared-any")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["env"] == "WEB_API"

        # 2. Через Telegram Bot
        bot_user_id = uuid7()
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers={
                "X-Internal-Token": settings.auth.internal_token,
                "X-User-Id": str(bot_user_id),
                "X-Telegram-Id": "777888",
            },
        ) as client:
            resp = await client.get("/shared-any")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["env"] == "TELEGRAM_BOT"
