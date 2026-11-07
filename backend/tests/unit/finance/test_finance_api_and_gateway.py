from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from uuid6 import uuid7

from src.api.main import app
from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.core.security import SystemRole, create_access_token
from src.modules.finance.dependencies import (
    get_currency_converter_service,
    get_finance_query_service,
    get_rate_sync_service,
)
from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider
from src.modules.finance.domain.models import ConversionResult, ExchangeRate
from src.modules.finance.public import FinancePublicGateway
from src.modules.finance.queries.dto import ExchangeRateResponseDTO
from tests.unit.fakes import FakeUnitOfWork


@pytest.mark.asyncio
async def test_finance_public_gateway_transaction_boundary() -> None:
    """
    Тест дотримання Інваріанту 7 (Контроль транзакцій):
    якщо передано зовнішній uow, публічний фасад не викликає commit самостійно.
    """
    external_uow = FakeUnitOfWork()
    mock_session = AsyncMock()

    dummy_rate = ExchangeRate(
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.2000"),
    )

    fake_client = AsyncMock()
    fake_client.provider = ExchangeRateProvider.NBU
    fake_client.fetch_rates = AsyncMock(return_value=[dummy_rate])

    gateway = FinancePublicGateway(
        session=mock_session,
        uow=external_uow,
        clients=[fake_client],
    )
    # Мокаємо метод репозиторію
    gateway._rate_repo.append_many = AsyncMock()  # type: ignore[method-assign]

    result = await gateway.sync_all_rates()

    assert result.synced_count == 1
    assert external_uow.committed is False  # Інваріант 7: commit не викликається!


@pytest.mark.asyncio
async def test_finance_public_gateway_self_commit() -> None:
    """
    Якщо зовнішній uow не передано, публічний фасад самостійно комітить сесію.
    """
    mock_session = AsyncMock()
    internal_uow = FakeUnitOfWork()

    dummy_rate = ExchangeRate(
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.2000"),
    )
    fake_client = AsyncMock()
    fake_client.provider = ExchangeRateProvider.NBU
    fake_client.fetch_rates = AsyncMock(return_value=[dummy_rate])

    gateway = FinancePublicGateway(
        session=mock_session,
        uow=None,
        clients=[fake_client],
    )
    gateway._uow = internal_uow
    gateway._rate_repo.append_many = AsyncMock()  # type: ignore[method-assign]

    result = await gateway.sync_all_rates()

    assert result.synced_count == 1
    assert internal_uow.committed is True


@pytest.mark.asyncio
async def test_finance_public_gateway_convert_to_uah() -> None:
    """Публічний метод convert_to_uah повертає очікуваний DTO."""
    mock_session = AsyncMock()
    gateway = FinancePublicGateway(session=mock_session)

    conversion_result = ConversionResult(
        original_amount=Decimal("15.00"),
        original_currency=CurrencyCode.USD,
        amount_uah=Decimal("618.00"),
        rate_used=Decimal("41.2000"),
        provider_used=ExchangeRateProvider.MONOBANK,
        is_stale_fallback=False,
        rate_created_at=datetime.now(UTC),
    )
    gateway._converter_service.convert_to_uah = AsyncMock(return_value=conversion_result)  # type: ignore[method-assign]

    dto = await gateway.convert_to_uah(
        amount=Decimal("15.00"),
        currency="USD",
        preferred_bank="MONOBANK",
    )

    assert dto.amount_uah == Decimal("618.00")
    assert dto.rate_used == Decimal("41.2000")
    assert dto.provider_used == ExchangeRateProvider.MONOBANK
    assert dto.is_stale_fallback is False


@pytest.mark.asyncio
async def test_convert_currency_endpoint_success() -> None:
    """Ендпоінт POST /api/v1/finance/convert успішно конвертує суму."""
    user_id = uuid7()
    token = create_access_token(data={"sub": str(user_id), "username": "test_user", "role": SystemRole.USER.value})

    mock_converter = AsyncMock()
    mock_converter.convert_to_uah = AsyncMock(
        return_value=ConversionResult(
            original_amount=Decimal("20.00"),
            original_currency=CurrencyCode.USD,
            amount_uah=Decimal("830.00"),
            rate_used=Decimal("41.5000"),
            provider_used=ExchangeRateProvider.MONOBANK,
            is_stale_fallback=False,
            rate_created_at=datetime.now(UTC),
        )
    )

    app.dependency_overrides[get_currency_converter_service] = lambda: mock_converter

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.post(
                "/api/v1/finance/convert",
                json={"amount": "20.00", "currency": "USD", "preferred_bank": "MONOBANK"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["original_amount"] == "20.00"
        assert data["amount_uah"] == "830.00"
        assert data["rate_used"] == "41.5000"
        assert data["provider_used"] == "MONOBANK"
        assert data["is_stale_fallback"] is False
    finally:
        app.dependency_overrides.pop(get_currency_converter_service, None)


@pytest.mark.asyncio
async def test_get_latest_rates_endpoint_success() -> None:
    """Ендпоінт GET /api/v1/finance/rates/latest повертає зріз останніх курсів."""
    user_id = uuid7()
    token = create_access_token(data={"sub": str(user_id), "username": "test_user", "role": SystemRole.USER.value})

    mock_query_service = AsyncMock()
    mock_query_service.get_latest_rates = AsyncMock(
        return_value=[
            ExchangeRateResponseDTO(
                id=uuid7(),
                provider=ExchangeRateProvider.NBU,
                base_currency="UAH",
                target_currency="USD",
                rate_buy=Decimal("41.2500"),
                rate_sell=Decimal("41.2500"),
                created_at=datetime.now(UTC),
            )
        ]
    )

    app.dependency_overrides[get_finance_query_service] = lambda: mock_query_service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.get("/api/v1/finance/rates/latest")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["provider"] == "NBU"
        assert data[0]["target_currency"] == "USD"
    finally:
        app.dependency_overrides.pop(get_finance_query_service, None)


@pytest.mark.asyncio
async def test_get_rate_history_endpoint_success() -> None:
    """Ендпоінт GET /api/v1/finance/rates/history повертає пагіновану історію."""
    user_id = uuid7()
    token = create_access_token(data={"sub": str(user_id), "username": "test_user", "role": SystemRole.USER.value})

    mock_query_service = AsyncMock()
    mock_query_service.get_rate_history = AsyncMock(
        return_value=PaginatedResponse.create(
            items=[
                ExchangeRateResponseDTO(
                    id=uuid7(),
                    provider=ExchangeRateProvider.MONOBANK,
                    base_currency="UAH",
                    target_currency="USD",
                    rate_buy=Decimal("41.2000"),
                    rate_sell=Decimal("41.7500"),
                    created_at=datetime.now(UTC),
                )
            ],
            total=1,
            params=PaginationParams(page=1, size=20),
        )
    )

    app.dependency_overrides[get_finance_query_service] = lambda: mock_query_service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.get(
                "/api/v1/finance/rates/history",
                params={"provider": "MONOBANK", "target_currency": "USD", "page": 1, "size": 20},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["provider"] == "MONOBANK"
    finally:
        app.dependency_overrides.pop(get_finance_query_service, None)


@pytest.mark.asyncio
async def test_sync_rates_endpoint_forbidden_for_regular_user() -> None:
    """Користувач із роллю USER не має права викликати POST /api/v1/finance/rates/sync (403 Forbidden)."""
    user_id = uuid7()
    token = create_access_token(data={"sub": str(user_id), "username": "regular_user", "role": SystemRole.USER.value})

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        response = await client.post("/api/v1/finance/rates/sync")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sync_rates_endpoint_success_for_admin() -> None:
    """Користувач із роллю ADMIN має право викликати синхронізацію курсів (200 OK)."""
    admin_id = uuid7()
    token = create_access_token(data={"sub": str(admin_id), "username": "admin_user", "role": SystemRole.ADMIN.value})

    mock_sync_service = AsyncMock()
    from src.modules.finance.application.dto import SyncRatesResultDTO

    mock_sync_service.sync_all_rates = AsyncMock(
        return_value=SyncRatesResultDTO(
            synced_count=4,
            providers_succeeded=[ExchangeRateProvider.NBU, ExchangeRateProvider.MONOBANK],
            providers_failed={},
        )
    )

    app.dependency_overrides[get_rate_sync_service] = lambda: mock_sync_service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.post("/api/v1/finance/rates/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["synced_count"] == 4
        assert "NBU" in data["providers_succeeded"]
    finally:
        app.dependency_overrides.pop(get_rate_sync_service, None)
