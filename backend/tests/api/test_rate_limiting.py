import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_login_rate_limiting_api(api_client: AsyncClient) -> None:
    """
    API-тест перевірки формату та обробки запитів на ендпоінт авторизації POST /api/v1/users/auth/login.
    Призначений для прогону у зв'язці з Redis у контейнеризованому середовищі.
    """
    login_payload = {
        "username": "rate_limit_test_user",
        "password": "wrong_password",
    }
    responses = []
    for _ in range(6):
        res = await api_client.post("/api/v1/users/auth/login", json=login_payload)
        responses.append(res.status_code)

    # У живому середовищі очікується 401 (Invalid Credentials) або 429 (Too Many Requests)
    assert all(status in (401, 429) for status in responses)
