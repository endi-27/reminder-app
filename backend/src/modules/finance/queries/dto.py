from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.finance.domain.enums import ExchangeRateProvider


class ExchangeRateResponseDTO(BaseModel):
    """Схема вихідного представлення курсу валют для читання (Read-Side CQRS)."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[
        UUID,
        Field(description="Унікальний ідентифікатор запису курсу (UUIDv7)"),
    ]
    provider: Annotated[
        ExchangeRateProvider,
        Field(description="Джерело / банківський провайдер курсу"),
    ]
    base_currency: Annotated[
        str,
        Field(description="Базова валюта (за замовчуванням UAH)"),
    ]
    target_currency: Annotated[
        str,
        Field(description="Цільова іноземна валюта (USD, EUR)"),
    ]
    rate_buy: Annotated[
        Decimal | None,
        Field(default=None, description="Курс купівлі банком (для НБУ дорівнює курсу продажу)"),
    ] = None
    rate_sell: Annotated[
        Decimal,
        Field(description="Курс продажу / списання за карткою"),
    ]
    created_at: Annotated[
        datetime,
        Field(description="Дата та точний час фіксації курсу в системі (UTC)"),
    ]
