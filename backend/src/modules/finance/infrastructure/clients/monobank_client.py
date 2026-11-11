from decimal import Decimal
from typing import Any

import httpx

from src.core import logger, settings
from src.core.domain.enums import CurrencyCode
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.exceptions import BankProviderFetchError
from src.modules.finance.domain.interfaces import IBankRateProviderClient
from src.modules.finance.domain.models import ExchangeRate


class MonobankClient(IBankRateProviderClient):
    """Клієнт отримання комерційних курсів валют від Monobank."""

    provider: ExchangeRateProvider = ExchangeRateProvider.MONOBANK

    # Коди валют за стандартом ISO 4217 (Numeric)
    UAH_NUMERIC_CODE = 980
    TARGET_CURRENCY_MAP = {
        840: CurrencyCode.USD,
        978: CurrencyCode.EUR,
    }

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._api_url = api_url or settings.finance.monobank_api_url
        self._timeout = timeout or settings.finance.http_timeout_seconds

    async def fetch_rates(self) -> list[ExchangeRate]:
        """
        Отримує та парсить курси валют USD/UAH та EUR/UAH від публічного API Monobank.

        Підтримує як готівковий/картковий курс (rateBuy/rateSell), так і крос-курс (rateCross).
        """
        try:
            if self._client is not None:
                response = await self._client.get(self._api_url)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self._api_url)

            response.raise_for_status()
            data: Any = response.json()
        except Exception as exc:
            logger.warning(f"Помилка отримання курсу валют від Monobank ({self._api_url}): {exc}")
            raise BankProviderFetchError(f"Не вдалося отримати курси від Monobank: {exc}") from exc

        if not isinstance(data, list):
            raise BankProviderFetchError("Неочікуваний формат відповіді API Monobank (очікувався список).")

        rates: list[ExchangeRate] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            code_a = item.get("currencyCodeA")
            code_b = item.get("currencyCodeB")

            if code_b == self.UAH_NUMERIC_CODE and code_a in self.TARGET_CURRENCY_MAP:
                target_currency = self.TARGET_CURRENCY_MAP[code_a]

                raw_sell = item.get("rateSell")
                raw_buy = item.get("rateBuy")
                raw_cross = item.get("rateCross")

                rate_sell_val = raw_sell if raw_sell is not None else raw_cross
                if rate_sell_val is None:
                    continue

                rate_sell = Decimal(str(rate_sell_val)).quantize(Decimal("0.0001"))

                rate_buy: Decimal | None = None
                rate_buy_val = raw_buy if raw_buy is not None else raw_cross
                if rate_buy_val is not None:
                    rate_buy = Decimal(str(rate_buy_val)).quantize(Decimal("0.0001"))

                rates.append(
                    ExchangeRate(
                        provider=self.provider,
                        base_currency=CurrencyCode.UAH,
                        target_currency=target_currency,
                        rate_buy=rate_buy,
                        rate_sell=rate_sell,
                    )
                )

        return rates
