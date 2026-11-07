from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from uuid6 import uuid7

from src.core.security import SystemRole, create_access_token
from src.main import app
from src.modules.users.application.dto import (
    RegisterTelegramUserCommand,
)
from src.modules.users.domain.enums import ExchangeRateProvider, UserRole
from src.modules.users.domain.models import User
from src.modules.users.public import UsersPublicGateway, resolve_user_by_telegram_id
from src.modules.users.queries.dto import (
    UserResponseDTO,
    UserSettingsResponseDTO,
)
from tests.unit.fakes import FakeUnitOfWork


@pytest.mark.asyncio
async def test_users_public_gateway_transaction_boundary() -> None:
    """
    Тест дотримання Інваріанту 7 (Контроль транзакцій):
    зовнішній uow не комітиться всередині гейтвею.
    """
    external_uow = FakeUnitOfWork()
    mock_session = AsyncMock()

    gateway = UsersPublicGateway(session=mock_session, uow=external_uow)

    # Мокаємо Use Case всередині гейтвею
    fake_user = User(id=uuid7(), username="gateway_user")
    gateway._user_repo.get_by_telegram_id = AsyncMock(return_value=fake_user)  # type: ignore[method-assign]
    gateway._user_repo.save = AsyncMock()  # type: ignore[method-assign]

    user_dto = UserResponseDTO(
        id=fake_user.id,
        username=fake_user.username,
        role=fake_user.role,
        settings=UserSettingsResponseDTO(
            id=uuid7(),
            user_id=fake_user.id,
            timezone="Europe/Kyiv",
            quiet_hours_start=time(23, 0),
            quiet_hours_end=time(8, 0),
            preferred_bank=ExchangeRateProvider.MONOBANK,
            auto_deadline_priority_escalation=True,
            version=1,
            created_at=fake_user.created_at,
            updated_at=fake_user.updated_at,
        ),
        version=1,
        created_at=fake_user.created_at,
        updated_at=fake_user.updated_at,
    )
    gateway._query_service.get_by_id = AsyncMock(return_value=user_dto)  # type: ignore[method-assign]

    cmd = RegisterTelegramUserCommand(
        telegram_id=999,
        telegram_chat_id=999,
        tg_username="gateway_user",
    )

    result = await gateway.get_or_register_telegram_user(cmd)

    assert result.username == "gateway_user"
    # Оскільки uow зовнішній, commit() НЕ повинен викликатися гейтвеєм
    assert external_uow.committed is False


@pytest.mark.asyncio
async def test_resolve_user_by_telegram_id_found_and_not_found() -> None:
    """Тест резолвера CurrentUser за Telegram ID для глобальної автентифікації."""
    mock_session = AsyncMock()
    user_id = uuid7()
    now = datetime.now(UTC)

    user_dto = UserResponseDTO(
        id=user_id,
        username="tg_pilot",
        role=UserRole.USER,
        settings=UserSettingsResponseDTO(
            id=uuid7(),
            user_id=user_id,
            timezone="Europe/Kyiv",
            quiet_hours_start=time(23, 0),
            quiet_hours_end=time(8, 0),
            preferred_bank=ExchangeRateProvider.MONOBANK,
            auto_deadline_priority_escalation=True,
            version=1,
            created_at=now,
            updated_at=now,
        ),
        version=1,
        created_at=now,
        updated_at=now,
    )

    # 1. Користувача знайдено
    with pytest.MonkeyPatch.context() as mp:
        mock_qs = MagicMock()
        mock_qs.get_by_telegram_id = AsyncMock(return_value=user_dto)
        mp.setattr("src.modules.users.public.UserQueryService", lambda s: mock_qs)

        resolved = await resolve_user_by_telegram_id(12345, mock_session)
        assert resolved is not None
        assert resolved.id == user_id
        assert resolved.username == "tg_pilot"
        assert resolved.role == SystemRole.USER
        assert resolved.telegram_id == 12345

    # 2. Користувача не знайдено
    with pytest.MonkeyPatch.context() as mp:
        mock_qs = MagicMock()
        mock_qs.get_by_telegram_id = AsyncMock(return_value=None)
        mp.setattr("src.modules.users.public.UserQueryService", lambda s: mock_qs)

        resolved = await resolve_user_by_telegram_id(99999, mock_session)
        assert resolved is None


@pytest.mark.asyncio
async def test_users_api_endpoints() -> None:
    """Тест HTTP ендпоінтів модуля Users через TestClient / ASGITransport."""
    user_id = uuid7()
    token = create_access_token({"sub": str(user_id), "username": "api_user", "role": "USER"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Захист ендпоінта списку користувачів (тільки для ADMIN)
        res_forbidden = await client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_forbidden.status_code == 403

        # 2. Неавторизований запит до /me
        res_unauth = await client.get("/api/v1/users/me")
        assert res_unauth.status_code == 401

        # 3. Синхронізація Telegram без internal token відхиляється
        res_tg_unauth = await client.post(
            "/api/v1/users/telegram/sync",
            json={"telegram_id": 123, "telegram_chat_id": 123},
        )
        assert res_tg_unauth.status_code == 401
