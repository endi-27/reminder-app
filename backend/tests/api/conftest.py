from collections.abc import Callable
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core.config import settings
from src.core.security import SystemRole, create_access_token


@pytest.fixture
def bot_headers() -> dict[str, str]:
    """Стандартні заголовки для запитів від імені Telegram-бота."""
    return {"X-Internal-Token": settings.auth.internal_token}


@pytest.fixture
def auth_headers_factory() -> Callable[[UUID | None, str | None, SystemRole | None], dict[str, str]]:
    """
    Фабрика для генерації HTTP-заголовків Bearer JWT авторизації з заданим користувачем та роллю.
    """

    def _factory(
        user_id: UUID | None = None,
        username: str | None = None,
        role: SystemRole | None = None,
    ) -> dict[str, str]:
        target_id = user_id or uuid7()
        target_username = username or f"user_{target_id.hex[:6]}"
        target_role = role or SystemRole.USER
        token = create_access_token(
            {
                "sub": str(target_id),
                "username": target_username,
                "role": target_role.value,
            }
        )
        return {"Authorization": f"Bearer {token}"}

    return _factory
