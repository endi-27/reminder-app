from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from src.api.dependencies import AdminWebDep, CurrentUserDep
from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.core import limiter, settings
from src.core.domain.enums import CurrencyCode
from src.modules.finance.application.dto import (
    ConversionResultDTO,
    ConvertCurrencyQuery,
    SyncRatesResultDTO,
)
from src.modules.finance.application.services.currency_converter import CurrencyConverterService
from src.modules.finance.application.services.rate_sync_service import RateSyncService
from src.modules.finance.dependencies import (
    get_currency_converter_service,
    get_finance_query_service,
    get_rate_sync_service,
)
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.queries.dto import ExchangeRateResponseDTO
from src.modules.finance.queries.query_service import FinanceQueryService

finance_router = APIRouter(prefix="/finance", tags=["Finance"])


@finance_router.get(
    "/rates/latest",
    response_model=list[ExchangeRateResponseDTO],
    summary="Отримання останніх курсів валют",
    description=(
        "Повертає найсвіжіші доступні курси валют для всіх підтримуваних провайдерів (НБУ, Monobank, ПриватБанк)."
    ),
)
async def get_latest_rates(
    _: CurrentUserDep,
    query_service: Annotated[FinanceQueryService, Depends(get_finance_query_service)],
) -> list[ExchangeRateResponseDTO]:
    """Повертає зріз останніх актуальних курсів валют."""
    return await query_service.get_latest_rates()


@finance_router.get(
    "/rates/history",
    response_model=PaginatedResponse[ExchangeRateResponseDTO],
    summary="Отримання історії зміни курсів валют",
    description=(
        "Повертає пагіновану історію зміни курсу валюти для обраного постачальника у спадному хронологічному порядку."
    ),
)
async def get_rate_history(
    _: CurrentUserDep,
    provider: Annotated[
        ExchangeRateProvider,
        Query(description="Постачальник банківського курсу (NBU, MONOBANK, PRIVATBANK)"),
    ],
    target_currency: Annotated[
        CurrencyCode,
        Query(description="Код іноземної валюти (USD, EUR)"),
    ],
    params: Annotated[PaginationParams, Depends()],
    query_service: Annotated[FinanceQueryService, Depends(get_finance_query_service)],
) -> PaginatedResponse[ExchangeRateResponseDTO]:
    """Повертає історію змін курсів валюти із підтримкою розбивки на сторінки."""
    return await query_service.get_rate_history(
        provider=provider,
        target_currency=target_currency,
        params=params,
    )


@finance_router.post(
    "/convert",
    response_model=ConversionResultDTO,
    summary="Конвертація валюти у гривню (UAH)",
    description="Розраховує суму у гривнях (UAH) за курсом обраного банку або автоматичним fallback на НБУ.",
)
async def convert_currency(
    _: CurrentUserDep,
    query: ConvertCurrencyQuery,
    converter_service: Annotated[
        CurrencyConverterService,
        Depends(get_currency_converter_service),
    ],
) -> ConversionResultDTO:
    """Виконує розрахунок вартості у гривні з урахуванням свіжості банківських курсів."""
    result = await converter_service.convert_to_uah(
        amount=query.amount,
        currency=query.currency,
        preferred_bank=query.preferred_bank,
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


@finance_router.post(
    "/rates/sync",
    response_model=SyncRatesResultDTO,
    status_code=status.HTTP_200_OK,
    summary="Примусова синхронізація курсів валют (тільки адміністратори)",
    description=(
        "Запитує актуальні курси від НБУ, Monobank та ПриватБанку та зберігає їх у незмінну історію exchange_rates."
    ),
)
@limiter.limit(settings.rate_limit.bank_sync_limit)
async def sync_rates(
    request: Request,
    _admin: AdminWebDep,
    sync_service: Annotated[RateSyncService, Depends(get_rate_sync_service)],
) -> SyncRatesResultDTO:
    """Виконує повне оновлення курсів валют від зовнішніх API банків."""
    return await sync_service.sync_all_rates(commit=True)
