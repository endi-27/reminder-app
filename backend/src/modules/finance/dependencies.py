from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_uow
from src.core.database import get_db_session
from src.core.protocols import IUnitOfWork
from src.modules.finance.application.services.currency_converter import CurrencyConverterService
from src.modules.finance.application.services.rate_sync_service import RateSyncService
from src.modules.finance.domain.interfaces import (
    IBankRateProviderClient,
    IExchangeRateRepository,
)
from src.modules.finance.infrastructure.clients.monobank_client import MonobankClient
from src.modules.finance.infrastructure.clients.nbu_client import NbuClient
from src.modules.finance.infrastructure.clients.privatbank_client import PrivatBankClient
from src.modules.finance.infrastructure.repository import SqlAlchemyExchangeRateRepository
from src.modules.finance.public import FinancePublicGateway
from src.modules.finance.queries.query_service import FinanceQueryService


def get_exchange_rate_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IExchangeRateRepository:
    """Фабрика створення репозиторію курсів валют."""
    return SqlAlchemyExchangeRateRepository(session)


def get_finance_query_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FinanceQueryService:
    """Фабрика створення CQRS Read-Side сервісу запитів курсів валют."""
    return FinanceQueryService(session)


def get_currency_converter_service(
    rate_repo: Annotated[IExchangeRateRepository, Depends(get_exchange_rate_repository)],
) -> CurrencyConverterService:
    """Фабрика сервісу конвертації валют."""
    return CurrencyConverterService(rate_repo=rate_repo)


def get_bank_rate_clients() -> list[IBankRateProviderClient]:
    """Фабрика списку клієнтів зовнішніх банківських провайдерів курсів."""
    return [NbuClient(), MonobankClient(), PrivatBankClient()]


def get_rate_sync_service(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    rate_repo: Annotated[IExchangeRateRepository, Depends(get_exchange_rate_repository)],
    clients: Annotated[list[IBankRateProviderClient], Depends(get_bank_rate_clients)],
) -> RateSyncService:
    """Фабрика сервісу синхронізації курсів валют."""
    return RateSyncService(uow=uow, rate_repo=rate_repo, clients=clients)


def get_finance_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
) -> FinancePublicGateway:
    """Фабрика публічного міжмодульного фасаду FinancePublicGateway."""
    return FinancePublicGateway(session=session, uow=uow)
