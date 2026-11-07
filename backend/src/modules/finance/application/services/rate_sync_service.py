from collections.abc import Sequence

from src.core import logger
from src.core.protocols import IUnitOfWork
from src.modules.finance.application.dto import SyncRatesResultDTO
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.interfaces import (
    IBankRateProviderClient,
    IExchangeRateRepository,
)
from src.modules.finance.domain.models import ExchangeRate


class RateSyncService:
    """Сервіс фонової або ручної синхронізації курсів валют від банківських API."""

    def __init__(
        self,
        uow: IUnitOfWork,
        rate_repo: IExchangeRateRepository,
        clients: Sequence[IBankRateProviderClient],
    ) -> None:
        self._uow = uow
        self._rate_repo = rate_repo
        self._clients = clients

    async def sync_all_rates(self, *, commit: bool = True) -> SyncRatesResultDTO:
        """
        Опитує всі налаштовані банківські сервіси та зберігає отримані курси в сховищі.

        Стійкий до помилок: якщо один із провайдерів тимчасово недоступний або повернув 429/500,
        помилка логується як warning, а курси інших банків успішно зберігаються.
        """
        collected_rates: list[ExchangeRate] = []
        providers_succeeded: list[ExchangeRateProvider] = []
        providers_failed: dict[str, str] = {}

        for client in self._clients:
            try:
                rates = await client.fetch_rates()
                collected_rates.extend(rates)
                providers_succeeded.append(client.provider)
                logger.info(f"Успішно отримано {len(rates)} курсів валют від провайдера {client.provider.value}.")
            except Exception as exc:
                error_msg = str(exc)
                providers_failed[client.provider.value] = error_msg
                logger.warning(f"Помилка синхронізації курсів від {client.provider.value}: {error_msg}")

        if collected_rates:
            await self._rate_repo.append_many(collected_rates)

        if commit:
            await self._uow.commit()

        return SyncRatesResultDTO(
            synced_count=len(collected_rates),
            providers_succeeded=providers_succeeded,
            providers_failed=providers_failed,
        )
