from collections.abc import Sequence
from typing import Protocol

from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider
from src.modules.finance.domain.models import ExchangeRate


class IExchangeRateRepository(Protocol):
    """Абстрактний інтерфейс репозиторію курсів валют (Append-Only сховище)."""

    async def append(self, rate: ExchangeRate) -> None:
        """Додає новий запис курсу обміну валют до сховища."""
        ...

    async def append_many(self, rates: Sequence[ExchangeRate]) -> None:
        """Пакетно додає кілька записів курсів валют до сховища."""
        ...

    async def get_latest(
        self,
        provider: ExchangeRateProvider,
        target_currency: CurrencyCode,
    ) -> ExchangeRate | None:
        """Повертає найсвіжіший зафіксований курс для заданого банку та валюти."""
        ...


class IBankRateProviderClient(Protocol):
    """Інтерфейс клієнта взаємодії з зовнішнім постачальником банківських курсів."""

    provider: ExchangeRateProvider

    async def fetch_rates(self) -> list[ExchangeRate]:
        """Отримує актуальні котирування валют від зовнішнього банківського сервісу."""
        ...
