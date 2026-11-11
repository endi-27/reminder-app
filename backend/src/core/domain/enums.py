import enum


class SystemRole(enum.StrEnum):
    """Системні ролі користувачів платформи."""

    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    USER = "USER"


class CurrencyCode(enum.StrEnum):
    """Підтримувані коди валют за стандартом ISO 4217."""

    UAH = "UAH"
    USD = "USD"
    EUR = "EUR"


class ClientEnvironment(enum.StrEnum):
    """Середовища / канали виклику API платформи."""

    WEB_API = "WEB_API"
    TELEGRAM_BOT = "TELEGRAM_BOT"
