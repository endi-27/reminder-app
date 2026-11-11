from decimal import Decimal
from typing import Any

import httpx

from src.core import logger, settings
from src.core.domain.enums import CurrencyCode
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.exceptions import BankProviderFetchError
from src.modules.finance.domain.interfaces import IBankRateProviderClient
from src.modules.finance.domain.models import ExchangeRate


class PrivatBankClient(IBankRateProviderClient):
    """Клієнт отримання безготівкових курсів валют від ПриватБанку."""

    provider: ExchangeRateProvider = ExchangeRateProvider.PRIVATBANK

    TARGET_CURRENCY_MAP = {
        "USD": CurrencyCode.USD,
        "EUR": CurrencyCode.EUR,
    }

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._api_url = api_url or settings.finance.privatbank_api_url
        self._timeout = timeout or settings.finance.http_timeout_seconds

    async def fetch_rates(self) -> list[ExchangeRate]:
        """Отримує та парсить безготівкові курси USD та EUR від API ПриватБанку."""
        try:
            if self._client is not None:
                response = await self._client.get(self._api_url)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self._api_url)

            response.raise_for_status()
            data: Any = response.json()
        except Exception as exc:
            logger.warning(f"Помилка отримання курсу валют від ПриватБанку ({self._api_url}): {exc}")
            raise BankProviderFetchError(f"Не вдалося отримати курси від ПриватБанку: {exc}") from exc

        if not isinstance(data, list):
            raise BankProviderFetchError("Неочікуваний формат відповіді API ПриватБанку (очікувався список).")

        rates: list[ExchangeRate] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            base_ccy = item.get("base_ccy")
            ccy = item.get("ccy")

            if base_ccy == "UAH" and ccy in self.TARGET_CURRENCY_MAP:
                target_currency = self.TARGET_CURRENCY_MAP[ccy]
                raw_buy = item.get("buy")
                raw_sale = item.get("sale")

                if raw_sale is None:
                    continue

                rate_sell = Decimal(str(raw_sale)).quantize(Decimal("0.0001"))
                rate_buy: Decimal | None = None
                if raw_buy is not None:
                    rate_buy = Decimal(str(raw_buy)).quantize(Decimal("0.0001"))

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
