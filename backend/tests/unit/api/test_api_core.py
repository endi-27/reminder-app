from collections.abc import AsyncGenerator
from datetime import timedelta
from typing import Annotated
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Column, Integer, String, Table, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError
from uuid6 import uuid7

from src.api.dependencies import (
    CurrentUserDep,
    PublisherDep,
    SessionDep,
    UoWDep,
    get_current_user,
    get_notification_publisher,
    get_uow,
    register_telegram_user_resolver,
    require_role,
    verify_bot_internal_token,
)
from src.api.main import app
from src.api.schemas import (
    PaginatedResponse,
    PaginationParams,
    SortOrder,
    VersionedUpdateSchema,
    apply_sorting,
)
from src.core.config import settings
from src.core.context import (
    get_current_user_id,
    get_current_username,
)
from src.core.database import get_db_session
from src.core.exceptions import (
    ForbiddenException,
    IncompatibleScheduleLogicError,
    NotFoundException,
    UnauthorizedException,
)
from src.core.redis import get_redis_client
from src.core.security import CurrentUser, SystemRole, create_access_token
from src.infrastructure.db.base import Base
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications.redis_queue_publisher import RedisQueuePublisher


class TestPaginationAndOccSchemas:
    """Тестування схем пагінації, оптимістичного блокування та сортування."""

    def test_pagination_params_defaults(self) -> None:
        """Перевірка значень за замовчуванням для PaginationParams."""
        params = PaginationParams()
        assert params.page == 1
        assert params.size == 20
        assert params.offset == 0
        assert params.limit == 20

    def test_pagination_params_custom(self) -> None:
        """Перевірка кастомних значень та розрахунку offset і limit."""
        params = PaginationParams(page=3, size=15)
        assert params.page == 3
        assert params.size == 15
        assert params.offset == 30
        assert params.limit == 15

    def test_pagination_params_validation_errors(self) -> None:
        """Перевірка обмежень ge=1 та le=100 для пагінації."""
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

        with pytest.raises(ValidationError):
            PaginationParams(size=0)

        with pytest.raises(ValidationError):
            PaginationParams(size=101)

        with pytest.raises(ValidationError):
            PaginationParams(extra_field="invalid")  # type: ignore[call-arg]

    def test_paginated_response_create(self) -> None:
        """Перевірка створення пагінованої відповіді з автоматичним розрахунком сторінок."""
        items = ["item1", "item2", "item3"]
        params = PaginationParams(page=1, size=2)
        resp = PaginatedResponse.create(items=items, total=5, params=params)

        assert resp.items == items
        assert resp.total == 5
        assert resp.page == 1
        assert resp.size == 2
        assert resp.pages == 3

    def test_paginated_response_empty(self) -> None:
        """Перевірка розрахунку сторінок при нульовій кількості записів."""
        params = PaginationParams(page=1, size=20)
        resp: PaginatedResponse[str] = PaginatedResponse.create(items=[], total=0, params=params)

        assert resp.items == []
        assert resp.total == 0
        assert resp.pages == 0

    def test_versioned_update_schema(self) -> None:
        """Перевірка валідації схеми оптимістичного блокування VersionedUpdateSchema."""
        schema = VersionedUpdateSchema(version=1)
        assert schema.version == 1

        with pytest.raises(ValidationError):
            VersionedUpdateSchema(version=0)

        with pytest.raises(ValidationError):
            VersionedUpdateSchema(version=-1)

        with pytest.raises(ValidationError):
            VersionedUpdateSchema(version=1, extra_field=123)  # type: ignore[call-arg]

    def test_sorting_apply(self) -> None:
        """Перевірка застосування функції apply_sorting до SQL-запиту."""
        test_table = Table(
            "test_table",
            Base.metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String),
            Column("created_at", Integer),
        )

        allowed = {
            "name": test_table.c.name,
            "created_at": test_table.c.created_at,
        }

        # 1. Сортування за дозволеним полем ASC
        stmt = select(test_table)
        sorted_stmt = apply_sorting(
            stmt=stmt,
            sort_by="name",
            sort_order=SortOrder.ASC,
            allowed_columns=allowed,
            default_column=test_table.c.id,
        )
        assert "ORDER BY test_table.name ASC" in str(sorted_stmt)

        # 2. Сортування за дозволеним полем DESC
        sorted_stmt_desc = apply_sorting(
            stmt=stmt,
            sort_by="created_at",
            sort_order=SortOrder.DESC,
            allowed_columns=allowed,
            default_column=test_table.c.id,
        )
        assert "ORDER BY test_table.created_at DESC" in str(sorted_stmt_desc)

        # 3. Невідоме поле — фолбек на default_column
        sorted_fallback = apply_sorting(
            stmt=stmt,
            sort_by="unknown_col",
            sort_order=SortOrder.DESC,
            allowed_columns=allowed,
            default_column=test_table.c.id,
        )
        assert "ORDER BY test_table.id DESC" in str(sorted_fallback)


class TestHealthCheckAndRootEndpoints:
    """Тестування ендпоінтів перевірки стану системи /health та /."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self) -> None:
        """Перевірка кореневого ендпоінта системи GET /."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "Reminder App Backend"
            assert data["version"] == "0.1.0"
            assert data["health"] == "/api/v1/health"

    @pytest.mark.asyncio
    async def test_health_check_healthy(self) -> None:
        """Перевірка ендпоінта /api/v1/health при справних БД та Redis (200 OK)."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()

        async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_redis_client] = lambda: mock_redis

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert data["database"] == "ok"
                assert data["redis"] == "ok"
                assert data["version"] == "0.1.0"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_health_check_database_unhealthy(self) -> None:
        """Перевірка ендпоінта /api/v1/health при збої PostgreSQL (503 Service Unavailable)."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.side_effect = RuntimeError("Connection timeout to PostgreSQL")

        async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_redis_client] = lambda: mock_redis

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/health")
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "unhealthy"
                assert "unhealthy" in data["database"]
                assert data["redis"] == "ok"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_health_check_redis_unhealthy(self) -> None:
        """Перевірка ендпоінта /api/v1/health при збої Redis (503 Service Unavailable)."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()

        async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = ConnectionError("Cannot connect to Redis server")

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_redis_client] = lambda: mock_redis

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/health")
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "unhealthy"
                assert data["database"] == "ok"
                assert "unhealthy" in data["redis"]
        finally:
            app.dependency_overrides.clear()


class TestAuthDependencies:
    """Тестування автентифікації, авторизації (RBAC) та сервісних токенів."""

    def test_verify_bot_internal_token(self) -> None:
        """Перевірка валідації внутрішнього сервісного токена бота."""
        # Валідний токен
        verify_bot_internal_token(x_internal_token=settings.auth.internal_token)

        # Невалідний токен
        with pytest.raises(UnauthorizedException) as exc_info:
            verify_bot_internal_token(x_internal_token="invalid_token")
        assert "Недійсний або відсутній внутрішній сервісний токен." in exc_info.value.message

        # Відсутній токен
        with pytest.raises(UnauthorizedException):
            verify_bot_internal_token(x_internal_token=None)

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self) -> None:
        """Перевірка виклику get_current_user без жодних облікових даних."""
        session = AsyncMock(spec=AsyncSession)
        with pytest.raises(UnauthorizedException) as exc_info:
            await get_current_user(session=session)
        assert "Необхідна автентифікація" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_current_user_internal_token_with_user_id(self) -> None:
        """Перевірка автентифікації за X-Internal-Token та X-User-Id."""
        session = AsyncMock(spec=AsyncSession)
        user_id = uuid7()
        user = await get_current_user(
            session=session,
            x_internal_token=settings.auth.internal_token,
            x_telegram_id=987654321,
            x_user_id=user_id,
        )

        assert user.id == user_id
        assert user.telegram_id == 987654321
        assert user.username == "tg_987654321"
        assert user.role == SystemRole.USER
        assert get_current_user_id() == user_id
        assert get_current_username() == "tg_987654321"

    @pytest.mark.asyncio
    async def test_get_current_user_internal_token_with_resolver(self) -> None:
        """Перевірка автентифікації бота із зареєстрованим резолвером користувача."""
        session = AsyncMock(spec=AsyncSession)
        user_id = uuid7()
        expected_user = CurrentUser(
            id=user_id,
            username="alex_tg",
            role=SystemRole.USER,
            telegram_id=555111,
        )

        async def _fake_resolver(tg_id: int, s: AsyncSession) -> CurrentUser | None:
            if tg_id == 555111:
                return expected_user
            return None

        register_telegram_user_resolver(_fake_resolver)

        resolved = await get_current_user(
            session=session,
            x_internal_token=settings.auth.internal_token,
            x_telegram_id=555111,
        )
        assert resolved == expected_user
        assert get_current_user_id() == user_id
        assert get_current_username() == "alex_tg"

        # Неіснуючий Telegram ID без x_user_id
        with pytest.raises(UnauthorizedException) as exc_info:
            await get_current_user(
                session=session,
                x_internal_token=settings.auth.internal_token,
                x_telegram_id=999999,
            )
        assert "Користувача з вказаним Telegram ID не знайдено" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_current_user_internal_token_invalid(self) -> None:
        """Перевірка помилки недійсного внутрішнього токена."""
        session = AsyncMock(spec=AsyncSession)
        with pytest.raises(UnauthorizedException) as exc_info:
            await get_current_user(
                session=session,
                x_internal_token="wrong_token",
                x_user_id=uuid7(),
            )
        assert "Недійсний внутрішній сервісний токен." in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_current_user_jwt_valid(self) -> None:
        """Перевірка автентифікації через валідний Bearer JWT."""
        session = AsyncMock(spec=AsyncSession)
        user_id = uuid7()
        token = create_access_token(
            {
                "sub": str(user_id),
                "username": "john_doe",
                "role": SystemRole.ADMIN.value,
                "telegram_id": 123456,
            }
        )

        user = await get_current_user(
            session=session,
            authorization=f"Bearer {token}",
        )
        assert user.id == user_id
        assert user.username == "john_doe"
        assert user.role == SystemRole.ADMIN
        assert user.telegram_id == 123456
        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_get_current_user_jwt_expired(self) -> None:
        """Перевірка відхилення простроченого JWT токена."""
        session = AsyncMock(spec=AsyncSession)
        user_id = uuid7()
        expired_token = create_access_token(
            {"sub": str(user_id), "username": "old_user"},
            expires_delta=timedelta(seconds=-10),
        )

        with pytest.raises(UnauthorizedException) as exc_info:
            await get_current_user(
                session=session,
                authorization=f"Bearer {expired_token}",
            )
        assert "Термін дії токена закінчився." in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_current_user_jwt_invalid(self) -> None:
        """Перевірка невалідного формату або підпису токена."""
        session = AsyncMock(spec=AsyncSession)
        with pytest.raises(UnauthorizedException) as exc_info:
            await get_current_user(
                session=session,
                authorization="Bearer completely.invalid.token",
            )
        assert "Недійсний токен автентифікації." in exc_info.value.message

    @pytest.mark.asyncio
    async def test_require_role_rbac(self) -> None:
        """Перевірка фабрики обмеження доступу за системними ролями require_role."""
        admin_checker = require_role(SystemRole.ADMIN)

        # 1. SUPER_ADMIN завжди має доступ
        super_admin = CurrentUser(
            id=uuid7(),
            username="super",
            role=SystemRole.SUPER_ADMIN,
        )
        result = await admin_checker(current_user=super_admin)
        assert result == super_admin

        # 2. ADMIN має доступ до адмін-ендпоінта
        admin_user = CurrentUser(
            id=uuid7(),
            username="admin",
            role=SystemRole.ADMIN,
        )
        result = await admin_checker(current_user=admin_user)
        assert result == admin_user

        # 3. Звичайний USER не має доступу
        normal_user = CurrentUser(
            id=uuid7(),
            username="regular_user",
            role=SystemRole.USER,
        )
        with pytest.raises(ForbiddenException) as exc_info:
            await admin_checker(current_user=normal_user)
        assert "Недостатньо прав для виконання цієї дії." in exc_info.value.message


class TestExceptionHandlersAndMiddlewares:
    """Тестування обробників винятків, JSON-структури помилок та мідлварів."""

    @pytest.mark.asyncio
    async def test_stale_data_error_handler_occ(self) -> None:
        """Перевірка перехоплення StaleDataError -> 409 OPTIMISTIC_LOCK_CONFLICT (Інваріант 11)."""
        test_router = APIRouter()

        @test_router.get("/test-stale-data")
        async def trigger_stale_data() -> None:
            raise StaleDataError(None, "OCC version mismatch")

        app.include_router(test_router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test-stale-data")
            assert response.status_code == 409
            data = response.json()
            assert "error" in data
            assert data["error"]["code"] == "OPTIMISTIC_LOCK_CONFLICT"
            assert "Дані було змінено іншим процесом" in data["error"]["message"]
            assert data["error"]["details"]["reason"] == "concurrent_modification"
            assert "correlation_id" in data["error"]

    @pytest.mark.asyncio
    async def test_app_exception_handler(self) -> None:
        """Перевірка перехоплення AppException (наприклад, IncompatibleScheduleLogicError)."""
        test_router = APIRouter()

        @test_router.get("/test-domain-error")
        async def trigger_domain_error() -> None:
            raise IncompatibleScheduleLogicError(
                "Обрана логіка планування не підтримується для цього типу нагадування."
            )

        @test_router.get("/test-not-found-error")
        async def trigger_not_found() -> None:
            raise NotFoundException("Нагадування не знайдено.")

        app.include_router(test_router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Domain exception
            resp1 = await client.get("/test-domain-error")
            assert resp1.status_code == 400
            data1 = resp1.json()
            assert data1["error"]["code"] == "INCOMPATIBLE_SCHEDULE_LOGIC"
            assert "Обрана логіка планування" in data1["error"]["message"]

            # 2. Not found exception
            resp2 = await client.get("/test-not-found-error")
            assert resp2.status_code == 404
            data2 = resp2.json()
            assert data2["error"]["code"] == "NOT_FOUND"
            assert "Нагадування не знайдено." in data2["error"]["message"]

    @pytest.mark.asyncio
    async def test_validation_error_handler_masking(self) -> None:
        """Перевірка маскування паролів у помилках валідації 422 VALIDATION_ERROR."""
        test_router = APIRouter()

        class UserCreateTestSchema(BaseModel):
            username: Annotated[str, Field(min_length=3)]
            password: Annotated[str, Field(min_length=8)]

        @test_router.post("/test-validation-mask")
        async def trigger_validation(payload: UserCreateTestSchema) -> dict[str, str]:
            return {"status": "ok"}

        app.include_router(test_router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/test-validation-mask",
                json={"username": "ab", "password": "short"},
            )
            assert response.status_code == 422
            data = response.json()
            assert data["error"]["code"] == "VALIDATION_ERROR"
            errors = data["error"]["details"]["errors"]

            # Перевіряємо, що відкритий пароль замінено на ***MASKED***
            password_err = next(e for e in errors if "password" in e.get("loc", ()))
            assert password_err["input"] == "***MASKED***"

    @pytest.mark.asyncio
    async def test_integrity_error_handler(self) -> None:
        """Перевірка перехоплення IntegrityError (409 CONFLICT)."""
        test_router = APIRouter()

        @test_router.get("/test-integrity-error")
        async def trigger_integrity() -> None:
            class FakePGError(Exception):
                pgcode = "23505"

            raise IntegrityError("INSERT statement", {}, FakePGError("Unique violation"))

        app.include_router(test_router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test-integrity-error")
            assert response.status_code == 409
            data = response.json()
            assert data["error"]["code"] == "CONFLICT"
            assert data["error"]["details"]["pgcode"] == "23505"

    @pytest.mark.asyncio
    async def test_unhandled_exception_handler_500(self) -> None:
        """Перевірка перехоплення непередбаченої системної помилки 500 INTERNAL_ERROR."""
        test_router = APIRouter()

        @test_router.get("/test-unhandled-500")
        async def trigger_unexpected() -> None:
            raise RuntimeError("Критичний збій пам'яті чи стороннього сервісу")

        app.include_router(test_router)

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/test-unhandled-500")
            assert response.status_code == 500
            data = response.json()
            assert data["error"]["code"] == "INTERNAL_ERROR"
            assert data["error"]["message"] == "Сталася неочікувана внутрішня помилка сервера."

    @pytest.mark.asyncio
    async def test_middlewares_headers(self) -> None:
        """Перевірка встановлення діагностичних заголовків мідлварами."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Згенерований X-Correlation-ID
            resp = await client.get("/")
            assert "X-Correlation-ID" in resp.headers
            assert "X-Process-Time" in resp.headers

            # 2. Переданий X-Correlation-ID повинен повертатися клієнту
            custom_id = str(uuid7())
            resp_custom = await client.get("/", headers={"X-Correlation-ID": custom_id})
            assert resp_custom.headers["X-Correlation-ID"] == custom_id

            # 3. no_cache_response_middleware для шляхів /api/
            resp_api = await client.get("/api/v1/health")
            assert resp_api.headers.get("Cache-Control") == "no-store, no-cache, must-revalidate, max-age=0"


class TestUoWAndPublisherDependencies:
    """Тестування фабрик залежностей get_uow та get_notification_publisher."""

    def test_get_uow(self) -> None:
        """Перевірка створення SqlAlchemyUnitOfWork через get_uow."""
        mock_session = AsyncMock(spec=AsyncSession)
        uow = get_uow(session=mock_session)
        assert isinstance(uow, SqlAlchemyUnitOfWork)

    def test_get_notification_publisher(self) -> None:
        """Перевірка створення RedisQueuePublisher через get_notification_publisher."""
        mock_redis = AsyncMock()
        publisher = get_notification_publisher(redis=mock_redis)
        assert isinstance(publisher, RedisQueuePublisher)

    def test_dependency_type_aliases(self) -> None:
        """Перевірка коректності оголошення типізованих аліасів залежностей."""
        assert CurrentUserDep is not None
        assert PublisherDep is not None
        assert SessionDep is not None
        assert UoWDep is not None
