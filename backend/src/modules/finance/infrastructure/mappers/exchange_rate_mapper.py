from src.infrastructure.db.mappers import BaseMapper
from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider
from src.modules.finance.domain.models import ExchangeRate
from src.modules.finance.infrastructure.models import ExchangeRateModel


class ExchangeRateMapper(BaseMapper[ExchangeRate, ExchangeRateModel]):
    """Мапер між доменним записом ExchangeRate та ORM-моделлю ExchangeRateModel."""

    def to_domain(self, model: ExchangeRateModel) -> ExchangeRate:
        """Трансформація ORM-моделі ExchangeRateModel у доменний об'єкт ExchangeRate."""
        return ExchangeRate(
            id=model.id,
            provider=ExchangeRateProvider(model.provider),
            base_currency=CurrencyCode(model.base_currency),
            target_currency=CurrencyCode(model.target_currency),
            rate_buy=model.rate_buy,
            rate_sell=model.rate_sell,
            created_at=model.created_at,
        )

    def to_model(self, entity: ExchangeRate) -> ExchangeRateModel:
        """Трансформація доменного об'єкта ExchangeRate в ORM-модель ExchangeRateModel."""
        return ExchangeRateModel(
            id=entity.id,
            provider=entity.provider,
            base_currency=entity.base_currency.value,
            target_currency=entity.target_currency.value,
            rate_buy=entity.rate_buy,
            rate_sell=entity.rate_sell,
            created_at=entity.created_at,
        )
