from src.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)


class UserNotFoundError(NotFoundException):
    """Виняток: користувача з вказаним ідентифікатором або логіном не знайдено."""

    def __init__(self, message: str = "Користувача не знайдено.") -> None:
        super().__init__(message)


class UserAlreadyExistsError(ConflictException):
    """Виняток: користувач з таким логіном або обліковими даними вже існує."""

    def __init__(self, message: str = "Користувач з таким логіном вже існує.") -> None:
        super().__init__(message)


class TelegramAccountAlreadyLinkedError(ConflictException):
    """Виняток: Telegram-акаунт вже прив'язаний до іншого користувача."""

    def __init__(
        self,
        message: str = "Цей Telegram-акаунт вже прив'язаний до іншого облікового запису.",
    ) -> None:
        super().__init__(message)


class SuperAdminDeletionForbiddenError(ForbiddenException):
    """Виняток: спроба видалення облікового запису суперадміністратора."""

    def __init__(
        self,
        message: str = "Обліковий запис SuperAdmin не може бути видалений.",
    ) -> None:
        super().__init__(message)


class InvalidTimezoneError(ValidationException):
    """Виняток: передано недійсний ідентифікатор часового поясу IANA."""

    def __init__(self, message: str = "Вказано недійсний ідентифікатор часового поясу.") -> None:
        super().__init__(message)


class InvalidCredentialsError(UnauthorizedException):
    """Виняток: недійсні облікові дані для автентифікації."""

    def __init__(self, message: str = "Невірний логін або пароль.") -> None:
        super().__init__(message)
