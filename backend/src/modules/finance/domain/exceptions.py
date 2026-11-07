from src.core.exceptions import AppException, NotFoundException, ValidationException


class ExchangeRateNotFoundError(NotFoundException):
    """Виняток, коли обмінний курс для валюти відсутній і у вибраному банку, і в НБУ."""

    default_error_code: str = "EXCHANGE_RATE_NOT_FOUND"
    default_message: str = "Обмінний курс для вказаної валюти не знайдено."


class BankProviderFetchError(AppException):
    """Помилка отримання курсу від зовнішнього API банківського сервісу."""

    status_code: int = 502
    default_error_code: str = "BANK_PROVIDER_FETCH_ERROR"
    default_message: str = "Помилка взаємодії з зовнішнім банківським сервісом."


class UnsupportedCurrencyError(ValidationException):
    """Виняток передачі непідтримуваного коду валюти."""

    default_error_code: str = "UNSUPPORTED_CURRENCY"
    default_message: str = "Вказаний код валюти не підтримується системою."
