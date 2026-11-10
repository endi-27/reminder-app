from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from uuid6 import uuid7

from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider
from src.utils.datetime import ensure_utc_datetime, now_utc


@dataclass(frozen=True, kw_only=True)
class ExchangeRate:
    """Незмінний запис курсу обміну валют (Append-Only Snapshot)."""

    provider: ExchangeRateProvider
    target_currency: CurrencyCode
    rate_sell: Decimal
    rate_buy: Decimal | None = None
    base_currency: CurrencyCode = CurrencyCode.UAH
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=now_utc)

    def is_stale(self, reference_time: datetime | None = None, max_age_hours: int = 48) -> bool:
        """Перевіряє, чи перевищує вік курсу допустимий поріг застарілості."""
        ref = reference_time if reference_time is not None else now_utc()
        ref_utc = ensure_utc_datetime(ref)
        created_utc = ensure_utc_datetime(self.created_at)
        return (ref_utc - created_utc) > timedelta(hours=max_age_hours)
