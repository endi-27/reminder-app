from typing import Any


class BotApiError(Exception):
    """Базовий виняток помилки взаємодії Telegram-бота з HTTP API бекенду."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.message}"


class BotApiNotFoundError(BotApiError):
    """Помилка відсутності запитуваного ресурсу (HTTP 404 Not Found)."""

    def __init__(
        self,
        message: str = "Запитуваний ресурс не знайдено на сервері.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=404, message=message, details=details)


class BotApiConflictError(BotApiError):
    """Конфлікт стану або версії сутності OCC (HTTP 409 Conflict)."""

    def __init__(
        self,
        message: str = "Конфлікт оновлення даних або версії запису.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=409, message=message, details=details)


class BotApiValidationError(BotApiError):
    """Помилка валідації вхідних даних на бекенді (HTTP 400 Bad Request / 422 Unprocessable Entity)."""

    def __init__(
        self,
        status_code: int = 422,
        message: str = "Некоректні вхідні дані запиту.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, message=message, details=details)
