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


class TelegramAccountAlreadyExistsError(ConflictException):
    """Виняток: Telegram-акаунт з такими ідентифікаторами вже існує."""

    def __init__(
        self,
        message: str = "Telegram-акаунт з такими ідентифікаторами вже існує.",
    ) -> None:
        super().__init__(message)


class TelegramAccountNotFoundError(NotFoundException):
    """Виняток: запис Telegram-акаунта не знайдено."""

    def __init__(self, message: str = "Telegram-профіль не знайдено.") -> None:
        super().__init__(message)


class TelegramAccountInUseError(ConflictException):
    """Виняток: спроба видалення Telegram-акаунта, що наразі прив'язаний до користувача."""

    def __init__(
        self,
        message: str = "Заборонено видаляти Telegram-акаунт, доки він прив'язаний до користувача.",
    ) -> None:
        super().__init__(message)


class TelegramAccountNotLinkedError(NotFoundException):
    """Виняток: у користувача немає підключеного Telegram-акаунта."""

    def __init__(
        self,
        message: str = "У користувача відсутній прив'язаний Telegram-профіль.",
    ) -> None:
        super().__init__(message)


class SuperAdminDeletionForbiddenError(ForbiddenException):
    """Виняток: спроба видалення облікового запису суперадміністратора."""

    def __init__(
        self,
        message: str = "Обліковий запис SuperAdmin не може бути видалений.",
    ) -> None:
        super().__init__(message)


class SuperAdminActionForbiddenError(ForbiddenException):
    """Виняток: виконання адміністративної дії над SuperAdmin заборонено."""

    def __init__(
        self,
        message: str = "Виконання цієї операції над обліковим записом SuperAdmin заборонено.",
    ) -> None:
        super().__init__(message)


class SuperAdminAlreadyExistsError(ConflictException):
    """Виняток: спроба створення або призначення другого SuperAdmin."""

    def __init__(
        self,
        message: str = "У системі вже зареєстровано SuperAdmin. Створення другого заборонено.",
    ) -> None:
        super().__init__(message)


class SelfActionForbiddenError(ForbiddenException):
    """Виняток: виконання операції над самим собою заборонено правилами безпеки."""

    def __init__(
        self,
        message: str = "Виконання цієї операції над власним обліковим записом заборонено.",
    ) -> None:
        super().__init__(message)


class CannotChangeOwnRoleError(ForbiddenException):
    """Виняток: спроба користувача змінити власну системну роль."""

    def __init__(
        self,
        message: str = "Зміна власної системної ролі заборонена.",
    ) -> None:
        super().__init__(message)


class UserDeactivatedError(ForbiddenException):
    """Виняток: спроба доступу або дії для деактивованого облікового запису."""

    def __init__(
        self,
        message: str = "Обліковий запис деактивовано.",
    ) -> None:
        super().__init__(message)


class PasswordNotSetError(ValidationException):
    """Виняток: у користувача відсутній встановлений пароль."""

    def __init__(
        self,
        message: str = "Пароль не встановлено. Зверніться до адміністратора для встановлення пароля.",
    ) -> None:
        super().__init__(message)


class InvalidCurrentPasswordError(ValidationException):
    """Виняток: недійсний поточний пароль під час зміни пароля."""

    def __init__(
        self,
        message: str = "Вказано невірний поточний пароль.",
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
