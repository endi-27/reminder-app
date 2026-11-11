import enum


class ExchangeRateProvider(enum.StrEnum):
    """Постачальники курсів валют для фінансових розрахунків та підписок."""

    NBU = "NBU"
    MONOBANK = "MONOBANK"
    PRIVATBANK = "PRIVATBANK"
