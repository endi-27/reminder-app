from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import distinct_on

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.core.domain.enums import CurrencyCode
from src.infrastructure.db.queries import BaseQueryService
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.infrastructure.models import ExchangeRateModel
from src.modules.finance.queries.dto import ExchangeRateResponseDTO


class FinanceQueryService(BaseQueryService):
    """CQRS Read-Side сервіс вибірок даних курсів валют без мутації стану сховища."""

    def _map_exchange_rate(self, model: ExchangeRateModel) -> ExchangeRateResponseDTO:
        """Трансформація ORM-моделі курсу валют у вихідний DTO."""
        return ExchangeRateResponseDTO(
            id=model.id,
            provider=ExchangeRateProvider(model.provider),
            base_currency=model.base_currency.value,
            target_currency=model.target_currency.value,
            rate_buy=model.rate_buy,
            rate_sell=model.rate_sell,
            created_at=model.created_at,
        )

    async def get_latest_rates(self) -> list[ExchangeRateResponseDTO]:
        """
        Повертає найсвіжіші котирування для всіх доступних пар (провайдер, цільова валюта).

        Використовує PostgreSQL DISTINCT ON за індексом idx_exchange_rates_provider_currency_created
        для миттєвої вибірки останніх актуальних даних.
        """
        stmt = (
            select(ExchangeRateModel)
            .ext(distinct_on(ExchangeRateModel.provider, ExchangeRateModel.target_currency))
            .order_by(
                ExchangeRateModel.provider,
                ExchangeRateModel.target_currency,
                desc(ExchangeRateModel.created_at),
            )
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._map_exchange_rate(model) for model in models]

    async def get_rate_history(
        self,
        provider: ExchangeRateProvider,
        target_currency: CurrencyCode,
        params: PaginationParams,
    ) -> PaginatedResponse[ExchangeRateResponseDTO]:
        """
        Повертає пагіновану історію зміни курсів для конкретного банку та валюти.

        Записи відсортовані у хронологічно спадному порядку (найновіші спочатку).
        """
        count_stmt = (
            select(func.count())
            .select_from(ExchangeRateModel)
            .where(
                ExchangeRateModel.provider == provider,
                ExchangeRateModel.target_currency == target_currency,
            )
        )
        total = await self._session.scalar(count_stmt) or 0

        stmt = (
            select(ExchangeRateModel)
            .where(
                ExchangeRateModel.provider == provider,
                ExchangeRateModel.target_currency == target_currency,
            )
            .order_by(desc(ExchangeRateModel.created_at))
            .offset(params.offset)
            .limit(params.limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        items = [self._map_exchange_rate(model) for model in models]

        return PaginatedResponse.create(items=items, total=total, params=params)
