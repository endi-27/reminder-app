from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.enums import CurrencyCode
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.interfaces import IExchangeRateRepository
from src.modules.finance.domain.models import ExchangeRate
from src.modules.finance.infrastructure.mappers import ExchangeRateMapper
from src.modules.finance.infrastructure.models import ExchangeRateModel


class SqlAlchemyExchangeRateRepository(IExchangeRateRepository):
    """Репозиторій збереження та вибірки курсів валют (Append-Only сховище на базі SQLAlchemy 2.0)."""

    def __init__(
        self,
        session: AsyncSession,
        mapper: ExchangeRateMapper | None = None,
    ) -> None:
        self._session = session
        self._mapper = mapper or ExchangeRateMapper()

    async def append(self, rate: ExchangeRate) -> None:
        """Додає новий запис курсу валюти та фіксує його у поточній сесії."""
        model = self._mapper.to_model(rate)
        self._session.add(model)
        await self._session.flush()

    async def append_many(self, rates: Sequence[ExchangeRate]) -> None:
        """Пакетно додає колекцію записів курсів валют та виконує flush."""
        if not rates:
            return
        models = [self._mapper.to_model(rate) for rate in rates]
        self._session.add_all(models)
        await self._session.flush()

    async def get_latest(
        self,
        provider: ExchangeRateProvider,
        target_currency: CurrencyCode,
    ) -> ExchangeRate | None:
        """Повертає останній зафіксований курс для вказаного банку та цільової валюти."""
        stmt = (
            select(ExchangeRateModel)
            .where(
                ExchangeRateModel.provider == provider,
                ExchangeRateModel.target_currency == target_currency.value,
            )
            .order_by(desc(ExchangeRateModel.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._mapper.to_domain(model)
