import enum


class ExchangeRateProvider(enum.StrEnum):
    """Постачальники курсів валют для фінансових розрахунків та підписок."""

    NBU = "NBU"
    MONOBANK = "MONOBANK"
    PRIVATBANK = "PRIVATBANK"


class CurrencyCode(enum.StrEnum):
    """Підтримувані коди валют за стандартом ISO 4217."""

    UAH = "UAH"
    USD = "USD"
    EUR = "EUR"
