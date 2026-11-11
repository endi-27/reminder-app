from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

import pytest

from src.core.domain.enums import CurrencyCode
from src.modules.finance.application.services.currency_converter import CurrencyConverterService
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.exceptions import (
    ExchangeRateNotFoundError,
    UnsupportedCurrencyError,
)
from src.modules.finance.domain.interfaces import IExchangeRateRepository
from src.modules.finance.domain.models import ExchangeRate
from src.utils.datetime import now_utc


class InMemoryExchangeRateRepository(IExchangeRateRepository):
    """Швидкий тестовий дублер репозиторію курсів валют у пам'яті."""

    def __init__(self, initial_rates: list[ExchangeRate] | None = None) -> None:
        self.rates: list[ExchangeRate] = list(initial_rates or [])

    async def append(self, rate: ExchangeRate) -> None:
        self.rates.append(rate)

    async def append_many(self, rates: Sequence[ExchangeRate]) -> None:
        self.rates.extend(rates)

    async def get_latest(
        self,
        provider: ExchangeRateProvider,
        target_currency: CurrencyCode,
    ) -> ExchangeRate | None:
        matching = [r for r in self.rates if r.provider == provider and r.target_currency == target_currency]
        if not matching:
            return None
        # Повертаємо найновіший за created_at
        return max(matching, key=lambda r: r.created_at)


@pytest.mark.asyncio
async def test_convert_uah_to_uah_direct() -> None:
    """Конвертація гривні у гривню повертає 1:1 без звернення до курсів банку."""
    repo = InMemoryExchangeRateRepository()
    service = CurrencyConverterService(rate_repo=repo)

    result = await service.convert_to_uah(
        amount=Decimal("150.75"),
        currency=CurrencyCode.UAH,
        preferred_bank=ExchangeRateProvider.MONOBANK,
    )

    assert result.original_amount == Decimal("150.75")
    assert result.original_currency == CurrencyCode.UAH
    assert result.amount_uah == Decimal("150.75")
    assert result.rate_used == Decimal("1.0000")
    assert result.provider_used == ExchangeRateProvider.MONOBANK
    assert result.is_stale_fallback is False
    assert result.rate_created_at is None


@pytest.mark.asyncio
async def test_convert_usd_fresh_preferred_bank() -> None:
    """Конвертація за свіжим курсом обраного банку (< 48 годин)."""
    current_time = now_utc()
    fresh_rate = ExchangeRate(
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_buy=Decimal("41.2000"),
        rate_sell=Decimal("41.5000"),
        created_at=current_time - timedelta(hours=2),
    )
    repo = InMemoryExchangeRateRepository(initial_rates=[fresh_rate])
    service = CurrencyConverterService(rate_repo=repo)

    result = await service.convert_to_uah(
        amount=Decimal("10.00"),
        currency=CurrencyCode.USD,
        preferred_bank=ExchangeRateProvider.MONOBANK,
        now=current_time,
    )

    assert result.amount_uah == Decimal("415.00")
    assert result.rate_used == Decimal("41.5000")
    assert result.provider_used == ExchangeRateProvider.MONOBANK
    assert result.is_stale_fallback is False
    assert result.rate_created_at == fresh_rate.created_at


@pytest.mark.asyncio
async def test_convert_usd_stale_preferred_bank_fallback_to_nbu() -> None:
    """
    Конвертація валюти при застарілому курсі обраного банку (> 48 годин).
    Система зобов'язана автоматично використати актуальний курс НБУ (is_stale_fallback = True).
    """
    current_time = now_utc()
    stale_monobank_rate = ExchangeRate(
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_buy=Decimal("40.0000"),
        rate_sell=Decimal("40.5000"),
        created_at=current_time - timedelta(hours=50),  # > 48h (застарілий)
    )
    nbu_rate = ExchangeRate(
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.USD,
        rate_buy=Decimal("41.2500"),
        rate_sell=Decimal("41.2500"),
        created_at=current_time - timedelta(hours=5),
    )
    repo = InMemoryExchangeRateRepository(initial_rates=[stale_monobank_rate, nbu_rate])
    service = CurrencyConverterService(rate_repo=repo)

    result = await service.convert_to_uah(
        amount=Decimal("100.00"),
        currency=CurrencyCode.USD,
        preferred_bank=ExchangeRateProvider.MONOBANK,
        now=current_time,
    )

    assert result.amount_uah == Decimal("4125.00")
    assert result.rate_used == Decimal("41.2500")
    assert result.provider_used == ExchangeRateProvider.NBU
    assert result.is_stale_fallback is True
    assert result.rate_created_at == nbu_rate.created_at


@pytest.mark.asyncio
async def test_convert_missing_preferred_bank_uses_nbu() -> None:
    """Якщо для обраного банку взагалі немає записів, використовується курс НБУ."""
    current_time = now_utc()
    nbu_rate = ExchangeRate(
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.EUR,
        rate_sell=Decimal("44.5000"),
        created_at=current_time - timedelta(hours=1),
    )
    repo = InMemoryExchangeRateRepository(initial_rates=[nbu_rate])
    service = CurrencyConverterService(rate_repo=repo)

    result = await service.convert_to_uah(
        amount=Decimal("50.00"),
        currency=CurrencyCode.EUR,
        preferred_bank=ExchangeRateProvider.PRIVATBANK,
        now=current_time,
    )

    assert result.amount_uah == Decimal("2225.00")
    assert result.rate_used == Decimal("44.5000")
    assert result.provider_used == ExchangeRateProvider.NBU
    assert result.is_stale_fallback is True


@pytest.mark.asyncio
async def test_convert_stale_bank_and_no_nbu_uses_stale_rate() -> None:
    """Якщо курс банку застарілий, а НБУ взагалі відсутній, використовується застарілий курс як fallback."""
    current_time = now_utc()
    stale_rate = ExchangeRate(
        provider=ExchangeRateProvider.PRIVATBANK,
        target_currency=CurrencyCode.EUR,
        rate_sell=Decimal("43.0000"),
        created_at=current_time - timedelta(days=5),
    )
    repo = InMemoryExchangeRateRepository(initial_rates=[stale_rate])
    service = CurrencyConverterService(rate_repo=repo)

    result = await service.convert_to_uah(
        amount=Decimal("10.00"),
        currency=CurrencyCode.EUR,
        preferred_bank=ExchangeRateProvider.PRIVATBANK,
        now=current_time,
    )

    assert result.amount_uah == Decimal("430.00")
    assert result.rate_used == Decimal("43.0000")
    assert result.provider_used == ExchangeRateProvider.PRIVATBANK
    assert result.is_stale_fallback is True


@pytest.mark.asyncio
async def test_convert_missing_all_rates_raises_not_found() -> None:
    """Якщо жодного курсу для валюти немає, піднімається ExchangeRateNotFoundError."""
    repo = InMemoryExchangeRateRepository()
    service = CurrencyConverterService(rate_repo=repo)

    with pytest.raises(ExchangeRateNotFoundError):
        await service.convert_to_uah(
            amount=Decimal("10.00"),
            currency=CurrencyCode.USD,
            preferred_bank=ExchangeRateProvider.MONOBANK,
        )


@pytest.mark.asyncio
async def test_convert_unsupported_currency_raises_validation_error() -> None:
    """Непідтримуваний код валюти викликає UnsupportedCurrencyError."""
    repo = InMemoryExchangeRateRepository()
    service = CurrencyConverterService(rate_repo=repo)

    with pytest.raises(UnsupportedCurrencyError):
        await service.convert_to_uah(
            amount=Decimal("10.00"),
            currency="GBP",
        )


@pytest.mark.asyncio
async def test_convert_rounding_half_up() -> None:
    """Перевірка правильного округлення копійок за банківським правилом ROUND_HALF_UP."""
    current_time = now_utc()
    rate = ExchangeRate(
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.2555"),
        created_at=current_time,
    )
    repo = InMemoryExchangeRateRepository(initial_rates=[rate])
    service = CurrencyConverterService(rate_repo=repo)

    # 10.33 * 41.2555 = 426.169315 -> округлюється до 426.17
    result = await service.convert_to_uah(
        amount=Decimal("10.33"),
        currency=CurrencyCode.USD,
        preferred_bank=ExchangeRateProvider.NBU,
        now=current_time,
    )
    assert result.amount_uah == Decimal("426.17")
