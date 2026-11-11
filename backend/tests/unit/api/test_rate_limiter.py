from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.api.exception_handlers import rate_limit_exceeded_handler, setup_exception_handlers
from src.api.main import app
from src.core import limiter, settings


def test_rate_limit_settings() -> None:
    """Перевірка коректності конфігурації RateLimitSettings за замовчуванням."""
    cfg = settings.rate_limit
    assert cfg.enabled is True
    assert cfg.default_limit == "200/minute"
    assert cfg.auth_login_limit == "5/minute"
    assert cfg.password_change_limit == "5/minute"
    assert cfg.password_admin_limit == "10/minute"
    assert cfg.user_create_limit == "20/minute"
    assert cfg.reminder_write_limit == "30/minute"
    assert cfg.bank_sync_limit == "5/minute"


def test_rate_limit_exceeded_handler() -> None:
    """Перевірка обробника RateLimitExceeded та стандартизованої JSON-структури 429."""
    mock_request = MagicMock(spec=Request)
    mock_request.url.path = "/api/v1/users/auth/login"
    mock_request.client.host = "192.168.1.100"

    mock_limit = MagicMock()
    mock_limit.error_message = None
    mock_limit.limit = "5 per 1 minute"
    exc = RateLimitExceeded(mock_limit)

    response = rate_limit_exceeded_handler(mock_request, exc)
    assert response.status_code == 429

    import json

    body = json.loads(response.body.decode("utf-8"))
    assert "error" in body
    assert body["error"]["code"] == "TOO_MANY_REQUESTS"
    assert "Перевищено допустимий ліміт" in body["error"]["message"]
    assert body["error"]["details"]["limit"] == "5 per 1 minute"


@pytest.mark.asyncio
async def test_limiter_in_memory_blocks_after_limit() -> None:
    """Перевірка спрацювання блокування 429 на тестовому додатку з In-Memory сховищем."""
    test_limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["2/minute"],
        storage_uri="memory://",
        enabled=True,
    )

    test_app = FastAPI()
    test_app.state.limiter = test_limiter
    test_app.add_middleware(SlowAPIMiddleware)
    setup_exception_handlers(test_app)

    @test_app.get("/test-custom")
    @test_limiter.limit("1/minute")
    async def custom_endpoint(request: Request) -> dict[str, str]:
        return {"status": "ok"}

    @test_app.get("/test-default")
    async def default_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # 1. Тест кастомного ліміту (1/minute)
        res1 = await client.get("/test-custom")
        assert res1.status_code == 200

        res2 = await client.get("/test-custom")
        assert res2.status_code == 429
        data2 = res2.json()
        assert data2["error"]["code"] == "TOO_MANY_REQUESTS"

        # 2. Тест дефолтного ліміту (2/minute)
        res_def1 = await client.get("/test-default")
        assert res_def1.status_code == 200

        res_def2 = await client.get("/test-default")
        assert res_def2.status_code == 200

        res_def3 = await client.get("/test-default")
        assert res_def3.status_code == 429
        data_def3 = res_def3.json()
        assert data_def3["error"]["code"] == "TOO_MANY_REQUESTS"


def test_main_app_has_limiter_and_middlewares() -> None:
    """Перевірка реєстрації Limiter, SlowAPIMiddleware та ProxyHeadersMiddleware у робочому додатку."""
    assert hasattr(app.state, "limiter")
    assert app.state.limiter is limiter

    # Перевіряємо наявність мідлварів у стеку
    middleware_types = [m.cls for m in app.user_middleware]
    assert SlowAPIMiddleware in middleware_types
    assert ProxyHeadersMiddleware in middleware_types


def test_limiter_disabled_in_testing_env() -> None:
    """Перевірка, що в тестовому середовищі рейт-лімітер за замовчуванням вимкнено для юніт-тестів."""
    assert settings.is_testing is True
    assert limiter.enabled is False
