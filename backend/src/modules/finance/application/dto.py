from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider


class ConvertCurrencyQuery(BaseModel):
    """Параметри запиту на конвертацію грошової суми у гривню (UAH)."""

    amount: Annotated[
        Decimal,
        Field(gt=0, description="Сума у вихідній валюті"),
    ]
    currency: Annotated[
        CurrencyCode,
        Field(description="Код вихідної валюти (USD, EUR, UAH)"),
    ]
    preferred_bank: Annotated[
        ExchangeRateProvider,
        Field(
            default=ExchangeRateProvider.MONOBANK,
            description="Бажаний банк для отримання курсу розрахунку",
        ),
    ] = ExchangeRateProvider.MONOBANK


class ConversionResultDTO(BaseModel):
    """Результат розрахунку конвертації валюти у гривню (UAH)."""

    original_amount: Annotated[
        Decimal,
        Field(description="Вихідна сума в оригінальній валюті"),
    ]
    original_currency: Annotated[
        CurrencyCode,
        Field(description="Вихідна валюта розрахунку"),
    ]
    amount_uah: Annotated[
        Decimal,
        Field(description="Сума у гривнях (UAH) після конвертації"),
    ]
    rate_used: Annotated[
        Decimal,
        Field(description="Використаний обмінний курс"),
    ]
    provider_used: Annotated[
        ExchangeRateProvider,
        Field(description="Банк або джерело використаного курсу"),
    ]
    is_stale_fallback: Annotated[
        bool,
        Field(
            default=False,
            description="Ознака використання резервного курсу (застарілого або НБУ)",
        ),
    ] = False
    rate_created_at: Annotated[
        datetime | None,
        Field(
            default=None,
            description="Дата та час фіксації використаного курсу в базі даних",
        ),
    ] = None


class SyncRatesResultDTO(BaseModel):
    """Результат синхронізації курсів валют із банківськими API."""

    synced_count: Annotated[
        int,
        Field(ge=0, description="Кількість успішно збережених записів курсів валют"),
    ]
    providers_succeeded: Annotated[
        list[ExchangeRateProvider],
        Field(description="Список постачальників, чиї курси успішно синхронізовано"),
    ]
    providers_failed: Annotated[
        dict[str, str],
        Field(description="Відомості про помилки опитування банків (провайдер -> опис)"),
    ]
