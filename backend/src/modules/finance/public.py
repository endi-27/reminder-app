from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.protocols import IUnitOfWork
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.modules.finance.application.dto import (
    ConversionResultDTO,
    SyncRatesResultDTO,
)
from src.modules.finance.application.services.currency_converter import CurrencyConverterService
from src.modules.finance.application.services.rate_sync_service import RateSyncService
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.interfaces import IBankRateProviderClient
from src.modules.finance.infrastructure.clients.monobank_client import MonobankClient
from src.modules.finance.infrastructure.clients.nbu_client import NbuClient
from src.modules.finance.infrastructure.clients.privatbank_client import PrivatBankClient
from src.modules.finance.infrastructure.repository import SqlAlchemyExchangeRateRepository


class FinancePublicGateway:
    """
    Публічний фасад модуля фінансів для міжмодульної взаємодії (Інваріант 1).

    Забезпечує безпечну конвертацію грошових сум у гривню (UAH) для нагадувань-підписок,
    а також доступ до фонової та ручної синхронізації банківських курсів валют.
    """

    def __init__(
        self,
        session: AsyncSession,
        uow: IUnitOfWork | None = None,
        clients: Sequence[IBankRateProviderClient] | None = None,
    ) -> None:
        self._session = session
        self._external_uow = uow
        self._uow = uow or SqlAlchemyUnitOfWork(session=session)
        self._rate_repo = SqlAlchemyExchangeRateRepository(session=session)
        self._converter_service = CurrencyConverterService(rate_repo=self._rate_repo)
        self._clients = clients or [NbuClient(), MonobankClient(), PrivatBankClient()]

    async def convert_to_uah(
        self,
        amount: Decimal,
        currency: str,
        preferred_bank: str = "MONOBANK",
    ) -> ConversionResultDTO:
        """
        Конвертує грошову суму у гривню (UAH) за курсом обраного банку або НБУ.

        Використовується модулем reminders для розрахунку витрат на валютні підписки.
        """
        result = await self._converter_service.convert_to_uah(
            amount=amount,
            currency=currency,
            preferred_bank=preferred_bank,
        )
        return ConversionResultDTO(
            original_amount=result.original_amount,
            original_currency=result.original_currency,
            amount_uah=result.amount_uah,
            rate_used=result.rate_used,
            provider_used=result.provider_used,
            is_stale_fallback=result.is_stale_fallback,
            rate_created_at=result.rate_created_at,
        )

    async def sync_all_rates(self) -> SyncRatesResultDTO:
        """
        Виконує синхронізацію курсів валют від усіх налаштованих постачальників.

        Якщо фасад викликано в межах зовнішньої транзакції (передано зовнішній uow),
        виклик uow.commit() делегується ініціатору транзакції (Інваріант 7).
        """
        service = RateSyncService(
            uow=self._uow,
            rate_repo=self._rate_repo,
            clients=self._clients,
        )
        should_commit = self._external_uow is None
        return await service.sync_all_rates(commit=should_commit)


__all__ = [
    "ExchangeRateProvider",
    "FinancePublicGateway",
]
