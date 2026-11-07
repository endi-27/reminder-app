import enum

from src.core.security import SystemRole

# Доменний аліас системної ролі користувача
UserRole = SystemRole


class ExchangeRateProvider(enum.StrEnum):
    """Постачальники курсів валют для фінансових нагадувань."""

    NBU = "NBU"
    MONOBANK = "MONOBANK"
    PRIVATBANK = "PRIVATBANK"
