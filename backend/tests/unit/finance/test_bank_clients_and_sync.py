from decimal import Decimal

import httpx
import pytest

from src.core.domain.enums import CurrencyCode
from src.modules.finance.application.services.rate_sync_service import RateSyncService
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.exceptions import BankProviderFetchError
from src.modules.finance.domain.interfaces import IBankRateProviderClient
from src.modules.finance.domain.models import ExchangeRate
from src.modules.finance.infrastructure.clients.monobank_client import MonobankClient
from src.modules.finance.infrastructure.clients.nbu_client import NbuClient
from src.modules.finance.infrastructure.clients.privatbank_client import PrivatBankClient
from tests.unit.fakes import FakeUnitOfWork
from tests.unit.finance.test_currency_converter import InMemoryExchangeRateRepository


@pytest.mark.asyncio
async def test_nbu_client_fetch_success() -> None:
    """Успішне отримання та парсинг курсів НБУ."""
    mock_payload = [
        {"r030": 840, "txt": "Долар США", "rate": 41.2543, "cc": "USD"},
        {"r030": 978, "txt": "Євро", "rate": 44.1234, "cc": "EUR"},
        {"r030": 643, "txt": "Рубль", "rate": 0.45, "cc": "RUB"},  # Повинно ігноруватися
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NbuClient(client=http_client, api_url="https://mock.bank.gov.ua")
        rates = await client.fetch_rates()

    assert len(rates) == 2
    usd_rate = next(r for r in rates if r.target_currency == CurrencyCode.USD)
    eur_rate = next(r for r in rates if r.target_currency == CurrencyCode.EUR)

    assert usd_rate.provider == ExchangeRateProvider.NBU
    assert usd_rate.rate_buy == Decimal("41.2543")
    assert usd_rate.rate_sell == Decimal("41.2543")

    assert eur_rate.rate_buy == Decimal("44.1234")
    assert eur_rate.rate_sell == Decimal("44.1234")


@pytest.mark.asyncio
async def test_nbu_client_error_handling() -> None:
    """Обробка мережевої помилки або статусу 500 від НБУ."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NbuClient(client=http_client, api_url="https://mock.bank.gov.ua")
        with pytest.raises(BankProviderFetchError):
            await client.fetch_rates()


@pytest.mark.asyncio
async def test_monobank_client_fetch_success() -> None:
    """Успішне отримання курсів Monobank із підтримкою rateBuy/rateSell та rateCross."""
    mock_payload = [
        {
            "currencyCodeA": 840,
            "currencyCodeB": 980,
            "date": 1700000000,
            "rateBuy": 41.20,
            "rateSell": 41.75,
        },
        {
            "currencyCodeA": 978,
            "currencyCodeB": 980,
            "date": 1700000000,
            "rateCross": 44.50,
        },
        {
            "currencyCodeA": 840,
            "currencyCodeB": 978,
            "date": 1700000000,
            "rateCross": 0.93,  # Не UAH (currencyCodeB != 980) -> ігнорується
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MonobankClient(client=http_client, api_url="https://mock.monobank.ua")
        rates = await client.fetch_rates()

    assert len(rates) == 2
    usd_rate = next(r for r in rates if r.target_currency == CurrencyCode.USD)
    eur_rate = next(r for r in rates if r.target_currency == CurrencyCode.EUR)

    assert usd_rate.provider == ExchangeRateProvider.MONOBANK
    assert usd_rate.rate_buy == Decimal("41.2000")
    assert usd_rate.rate_sell == Decimal("41.7500")

    # Для EUR перевіряємо крос-курс
    assert eur_rate.rate_buy == Decimal("44.5000")
    assert eur_rate.rate_sell == Decimal("44.5000")


@pytest.mark.asyncio
async def test_monobank_client_rate_limit_error() -> None:
    """Обробка помилки 429 Too Many Requests від Monobank."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"errorDescription": "Too many requests"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MonobankClient(client=http_client, api_url="https://mock.monobank.ua")
        with pytest.raises(BankProviderFetchError):
            await client.fetch_rates()


@pytest.mark.asyncio
async def test_privatbank_client_fetch_success() -> None:
    """Успішне отримання безготівкових курсів ПриватБанку."""
    mock_payload = [
        {"ccy": "USD", "base_ccy": "UAH", "buy": "41.15000", "sale": "41.75000"},
        {"ccy": "EUR", "base_ccy": "UAH", "buy": "44.20000", "sale": "44.80000"},
        {"ccy": "PLN", "base_ccy": "UAH", "buy": "10.00", "sale": "10.50"},  # Ігнорується
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = PrivatBankClient(client=http_client, api_url="https://mock.privatbank.ua")
        rates = await client.fetch_rates()

    assert len(rates) == 2
    usd_rate = next(r for r in rates if r.target_currency == CurrencyCode.USD)
    eur_rate = next(r for r in rates if r.target_currency == CurrencyCode.EUR)

    assert usd_rate.provider == ExchangeRateProvider.PRIVATBANK
    assert usd_rate.rate_buy == Decimal("41.1500")
    assert usd_rate.rate_sell == Decimal("41.7500")

    assert eur_rate.rate_buy == Decimal("44.2000")
    assert eur_rate.rate_sell == Decimal("44.8000")


class FakeBankClient(IBankRateProviderClient):
    """Тестовий клієнт провайдера банку."""

    def __init__(
        self,
        provider: ExchangeRateProvider,
        rates: list[ExchangeRate] | None = None,
        should_fail: bool = False,
    ) -> None:
        self.provider = provider
        self.rates = rates or []
        self.should_fail = should_fail

    async def fetch_rates(self) -> list[ExchangeRate]:
        if self.should_fail:
            raise BankProviderFetchError(f"Сервер {self.provider.value} тимчасово перевантажений.")
        return self.rates


@pytest.mark.asyncio
async def test_rate_sync_service_all_succeed() -> None:
    """Повна успішна синхронізація всіх трьох постачальників курсів."""
    uow = FakeUnitOfWork()
    repo = InMemoryExchangeRateRepository()

    client_nbu = FakeBankClient(
        ExchangeRateProvider.NBU,
        [
            ExchangeRate(
                provider=ExchangeRateProvider.NBU,
                target_currency=CurrencyCode.USD,
                rate_sell=Decimal("41.2000"),
            ),
            ExchangeRate(
                provider=ExchangeRateProvider.NBU,
                target_currency=CurrencyCode.EUR,
                rate_sell=Decimal("44.0000"),
            ),
        ],
    )
    client_mono = FakeBankClient(
        ExchangeRateProvider.MONOBANK,
        [
            ExchangeRate(
                provider=ExchangeRateProvider.MONOBANK,
                target_currency=CurrencyCode.USD,
                rate_sell=Decimal("41.5000"),
            ),
        ],
    )

    sync_service = RateSyncService(
        uow=uow,
        rate_repo=repo,
        clients=[client_nbu, client_mono],
    )

    result = await sync_service.sync_all_rates(commit=True)

    assert result.synced_count == 3
    assert len(result.providers_succeeded) == 2
    assert result.providers_failed == {}
    assert uow.committed is True
    assert len(repo.rates) == 3


@pytest.mark.asyncio
async def test_rate_sync_service_partial_failure_resilience() -> None:
    """
    Тест стійкості до збоїв: якщо один банк повертає помилку,
    інші курси успішно зберігаються, а помилка фіксується у звіті.
    """
    uow = FakeUnitOfWork()
    repo = InMemoryExchangeRateRepository()

    client_nbu = FakeBankClient(
        ExchangeRateProvider.NBU,
        [
            ExchangeRate(
                provider=ExchangeRateProvider.NBU,
                target_currency=CurrencyCode.USD,
                rate_sell=Decimal("41.2000"),
            ),
        ],
    )
    # Monobank повертає помилку (наприклад 429)
    client_mono = FakeBankClient(
        ExchangeRateProvider.MONOBANK,
        should_fail=True,
    )
    client_privat = FakeBankClient(
        ExchangeRateProvider.PRIVATBANK,
        [
            ExchangeRate(
                provider=ExchangeRateProvider.PRIVATBANK,
                target_currency=CurrencyCode.USD,
                rate_sell=Decimal("41.7000"),
            ),
        ],
    )

    sync_service = RateSyncService(
        uow=uow,
        rate_repo=repo,
        clients=[client_nbu, client_mono, client_privat],
    )

    result = await sync_service.sync_all_rates(commit=False)

    assert result.synced_count == 2
    assert ExchangeRateProvider.NBU in result.providers_succeeded
    assert ExchangeRateProvider.PRIVATBANK in result.providers_succeeded
    assert ExchangeRateProvider.MONOBANK.value in result.providers_failed
    assert uow.committed is False  # Бо commit=False
    assert len(repo.rates) == 2
