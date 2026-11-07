from decimal import Decimal
from typing import Any

import httpx

from src.core import logger, settings
from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider
from src.modules.finance.domain.exceptions import BankProviderFetchError
from src.modules.finance.domain.interfaces import IBankRateProviderClient
from src.modules.finance.domain.models import ExchangeRate


class NbuClient(IBankRateProviderClient):
    """Клієнт отримання офіційних курсів валют від Національного банку України (НБУ)."""

    provider: ExchangeRateProvider = ExchangeRateProvider.NBU

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._api_url = api_url or settings.finance.nbu_api_url
        self._timeout = timeout or settings.finance.http_timeout_seconds

    async def fetch_rates(self) -> list[ExchangeRate]:
        """
        Отримує та парсить офіційні курси USD та EUR від API НБУ.

        Для НБУ курс купівлі та продажу є однаковим офіційним курсом.
        """
        target_currencies = {
            "USD": CurrencyCode.USD,
            "EUR": CurrencyCode.EUR,
        }

        try:
            if self._client is not None:
                response = await self._client.get(self._api_url)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self._api_url)

            response.raise_for_status()
            data: Any = response.json()
        except Exception as exc:
            logger.warning(f"Помилка отримання курсу валют від НБУ ({self._api_url}): {exc}")
            raise BankProviderFetchError(f"Не вдалося отримати курси від НБУ: {exc}") from exc

        if not isinstance(data, list):
            raise BankProviderFetchError("Неочікуваний формат відповіді API НБУ (очікувався список).")

        rates: list[ExchangeRate] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            currency_code_str = item.get("cc")
            if currency_code_str in target_currencies:
                raw_rate = item.get("rate")
                if raw_rate is None:
                    continue
                rate_decimal = Decimal(str(raw_rate)).quantize(Decimal("0.0001"))
                rates.append(
                    ExchangeRate(
                        provider=self.provider,
                        base_currency=CurrencyCode.UAH,
                        target_currency=target_currencies[currency_code_str],
                        rate_buy=rate_decimal,
                        rate_sell=rate_decimal,
                    )
                )

        return rates
