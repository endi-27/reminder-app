from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider
from src.modules.finance.domain.models import ExchangeRate
from src.modules.finance.infrastructure.mappers import ExchangeRateMapper
from src.modules.finance.infrastructure.models import ExchangeRateModel
from src.modules.finance.infrastructure.repository import SqlAlchemyExchangeRateRepository
from src.utils.datetime import now_utc


def test_exchange_rate_is_stale_boundary_conditions() -> None:
    """Тест граничних умов методу is_stale (48 годин)."""
    now = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)

    # 1. Свіжий курс (вік 47 годин 59 хвилин) -> False
    fresh_rate = ExchangeRate(
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.5000"),
        created_at=now - timedelta(hours=47, minutes=59),
    )
    assert fresh_rate.is_stale(reference_time=now, max_age_hours=48) is False

    # 2. Рівно 48 годин -> False (не перевищує поріг)
    exact_48h_rate = ExchangeRate(
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.5000"),
        created_at=now - timedelta(hours=48),
    )
    assert exact_48h_rate.is_stale(reference_time=now, max_age_hours=48) is False

    # 3. Застарілий курс (вік 48 годин і 1 секунда) -> True
    stale_rate = ExchangeRate(
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.5000"),
        created_at=now - timedelta(hours=48, seconds=1),
    )
    assert stale_rate.is_stale(reference_time=now, max_age_hours=48) is True


def test_exchange_rate_mapper_roundtrip() -> None:
    """Тест двосторонньої коректної трансформації через ExchangeRateMapper."""
    mapper = ExchangeRateMapper()
    rate_id = uuid7()
    created_at = now_utc()

    domain_entity = ExchangeRate(
        id=rate_id,
        provider=ExchangeRateProvider.PRIVATBANK,
        base_currency=CurrencyCode.UAH,
        target_currency=CurrencyCode.EUR,
        rate_buy=Decimal("44.2000"),
        rate_sell=Decimal("44.8000"),
        created_at=created_at,
    )

    # to_model
    model = mapper.to_model(domain_entity)
    assert isinstance(model, ExchangeRateModel)
    assert model.id == rate_id
    assert model.provider == ExchangeRateProvider.PRIVATBANK
    assert model.base_currency == "UAH"
    assert model.target_currency == "EUR"
    assert model.rate_buy == Decimal("44.2000")
    assert model.rate_sell == Decimal("44.8000")
    assert model.created_at == created_at

    # to_domain
    restored = mapper.to_domain(model)
    assert isinstance(restored, ExchangeRate)
    assert restored.id == domain_entity.id
    assert restored.provider == domain_entity.provider
    assert restored.base_currency == domain_entity.base_currency
    assert restored.target_currency == domain_entity.target_currency
    assert restored.rate_buy == domain_entity.rate_buy
    assert restored.rate_sell == domain_entity.rate_sell
    assert restored.created_at == domain_entity.created_at


@pytest.mark.asyncio
async def test_sqlalchemy_exchange_rate_repository_methods() -> None:
    """Тест методів append, append_many та get_latest у SqlAlchemyExchangeRateRepository."""
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()
    mock_session.flush = AsyncMock()
    repo = SqlAlchemyExchangeRateRepository(session=mock_session)

    rate = ExchangeRate(
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.5000"),
    )

    # 1. append
    await repo.append(rate)
    mock_session.add.assert_called_once()
    mock_session.flush.assert_awaited_once()

    # 2. append_many
    mock_session.reset_mock()
    await repo.append_many([rate, rate])
    mock_session.add_all.assert_called_once()
    mock_session.flush.assert_awaited_once()

    # append_many з порожнім списком не викликає flush
    mock_session.reset_mock()
    await repo.append_many([])
    mock_session.add_all.assert_not_called()
    mock_session.flush.assert_not_called()

    # 3. get_latest (знайдено)
    mock_session.reset_mock()
    mock_model = ExchangeRateModel(
        id=uuid7(),
        provider=ExchangeRateProvider.MONOBANK,
        base_currency="UAH",
        target_currency="USD",
        rate_buy=Decimal("41.0000"),
        rate_sell=Decimal("41.5000"),
        created_at=now_utc(),
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute = AsyncMock(return_value=mock_result)

    found = await repo.get_latest(ExchangeRateProvider.MONOBANK, CurrencyCode.USD)
    assert found is not None
    assert found.provider == ExchangeRateProvider.MONOBANK
    assert found.target_currency == CurrencyCode.USD
    assert found.rate_sell == Decimal("41.5000")

    # 4. get_latest (не знайдено)
    mock_result.scalar_one_or_none.return_value = None
    not_found = await repo.get_latest(ExchangeRateProvider.NBU, CurrencyCode.EUR)
    assert not_found is None
