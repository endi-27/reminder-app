from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from src.core import settings
from src.core.domain.enums import CurrencyCode
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.exceptions import (
    ExchangeRateNotFoundError,
    UnsupportedCurrencyError,
)
from src.modules.finance.domain.interfaces import IExchangeRateRepository
from src.modules.finance.domain.models import ConversionResult


class CurrencyConverterService:
    """Сервіс конвертації грошових сум у гривню (UAH) з урахуванням свіжості курсів та fallback-стратегій."""

    def __init__(
        self,
        rate_repo: IExchangeRateRepository,
        stale_rate_hours: int | None = None,
    ) -> None:
        self._rate_repo = rate_repo
        self._stale_rate_hours = stale_rate_hours if stale_rate_hours is not None else settings.finance.stale_rate_hours

    async def convert_to_uah(
        self,
        amount: Decimal,
        currency: CurrencyCode | str,
        preferred_bank: ExchangeRateProvider | str = ExchangeRateProvider.MONOBANK,
        now: datetime | None = None,
    ) -> ConversionResult:
        """
        Конвертує грошову суму у гривню (UAH) за курсом обраного банку або НБУ.

        Бізнес-правила:
        1. Якщо валюта UAH — повертає результат 1:1 без звернення до БД.
        2. Якщо валюта USD або EUR:
           - Шукає останній курс обраного банку (preferred_bank).
           - Якщо курс знайдено і його вік <= stale_rate_hours (48 год) — рахує суму за курсом продажу (rate_sell).
           - Якщо курс обраного банку відсутній або застарів (> 48 год):
             - Виконує автоматичний fallback на актуальний курс НБУ (is_stale_fallback = True).
             - Якщо курс НБУ відсутній, але є застарілий курс банку — використовує його з is_stale_fallback = True.
             - Якщо жодного курсу в базі немає — піднімає ExchangeRateNotFoundError.
        """
        # 1. Валідація та нормалізація коду валюти
        target_currency: CurrencyCode
        if isinstance(currency, str):
            try:
                target_currency = CurrencyCode(currency.strip().upper())
            except ValueError as exc:
                raise UnsupportedCurrencyError(f"Валюта '{currency}' не підтримується системою.") from exc
        else:
            target_currency = currency

        # 2. Нормалізація постачальника курсу банку
        bank_provider: ExchangeRateProvider
        if isinstance(preferred_bank, str):
            try:
                bank_provider = ExchangeRateProvider(preferred_bank.strip().upper())
            except ValueError:
                bank_provider = ExchangeRateProvider.MONOBANK
        else:
            bank_provider = preferred_bank

        # 3. Базовий випадок: національна валюта UAH
        if target_currency == CurrencyCode.UAH:
            amount_uah = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return ConversionResult(
                original_amount=amount,
                original_currency=CurrencyCode.UAH,
                amount_uah=amount_uah,
                rate_used=Decimal("1.0000"),
                provider_used=bank_provider,
                is_stale_fallback=False,
                rate_created_at=None,
            )

        # 4. Пошук останнього курсу для обраного банку
        bank_rate = await self._rate_repo.get_latest(bank_provider, target_currency)
        is_bank_rate_stale = (
            bank_rate.is_stale(reference_time=now, max_age_hours=self._stale_rate_hours)
            if bank_rate is not None
            else True
        )

        # 5. Якщо курс обраного банку свіжий (< 48 год)
        if bank_rate is not None and not is_bank_rate_stale:
            amount_uah = (amount * bank_rate.rate_sell).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return ConversionResult(
                original_amount=amount,
                original_currency=target_currency,
                amount_uah=amount_uah,
                rate_used=bank_rate.rate_sell,
                provider_used=bank_provider,
                is_stale_fallback=False,
                rate_created_at=bank_rate.created_at,
            )

        # 6. Fallback: якщо курс банку застарів або відсутній, пробуємо знайти курс НБУ
        if bank_provider != ExchangeRateProvider.NBU:
            nbu_rate = await self._rate_repo.get_latest(ExchangeRateProvider.NBU, target_currency)
            if nbu_rate is not None:
                amount_uah = (amount * nbu_rate.rate_sell).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                return ConversionResult(
                    original_amount=amount,
                    original_currency=target_currency,
                    amount_uah=amount_uah,
                    rate_used=nbu_rate.rate_sell,
                    provider_used=ExchangeRateProvider.NBU,
                    is_stale_fallback=True,
                    rate_created_at=nbu_rate.created_at,
                )

        # 7. Якщо НБУ відсутній, але є застарілий курс обраного банку — використовуємо його з прапорцем fallback
        if bank_rate is not None:
            amount_uah = (amount * bank_rate.rate_sell).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return ConversionResult(
                original_amount=amount,
                original_currency=target_currency,
                amount_uah=amount_uah,
                rate_used=bank_rate.rate_sell,
                provider_used=bank_provider,
                is_stale_fallback=True,
                rate_created_at=bank_rate.created_at,
            )

        # 8. Жодного курсу не знайдено
        raise ExchangeRateNotFoundError(f"Обмінний курс для валюти '{target_currency.value}' відсутній у системі.")
