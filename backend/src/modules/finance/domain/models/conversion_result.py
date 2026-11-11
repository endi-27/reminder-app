from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.core.domain.enums import CurrencyCode
from src.modules.finance.domain.enums import ExchangeRateProvider


@dataclass(frozen=True, kw_only=True)
class ConversionResult:
    """Результат розрахунку конвертації валюти у гривню (UAH)."""

    original_amount: Decimal
    original_currency: CurrencyCode
    amount_uah: Decimal
    rate_used: Decimal
    provider_used: ExchangeRateProvider
    is_stale_fallback: bool = False
    rate_created_at: datetime | None = None
