from typing import Any


class AppException(Exception):
    """Базовий клас винятків додатку."""

    status_code: int = 500
    default_error_code: str = "INTERNAL_SERVER_ERROR"
    default_message: str = "Сталася неочікувана помилка сервера."

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.error_code = error_code or self.default_error_code
        self.details = details or {}
        super().__init__(self.message)


class DataInconsistencyException(AppException):
    """Виняток порушення внутрішньої узгодженості даних (наприклад, стан після коміту)."""

    status_code: int = 500
    default_error_code: str = "INTERNAL_DATA_INCONSISTENCY"
    default_message: str = "Виявлено внутрішню неузгодженість даних системи."


class NotFoundException(AppException):
    """Виняток, коли запитуваний ресурс не знайдено."""

    status_code: int = 404
    default_error_code: str = "NOT_FOUND"
    default_message: str = "Запитуваний ресурс не знайдено."


class ConflictException(AppException):
    """Виняток конфлікту стану ресурсу."""

    status_code: int = 409
    default_error_code: str = "CONFLICT"
    default_message: str = "Конфлікт стану ресурсу."


class UserAlreadyExistsException(ConflictException):
    """Виняток спроби створення або реєстрації користувача з уже зайнятим логіном."""

    default_error_code: str = "USER_ALREADY_EXISTS"
    default_message: str = "Користувач із таким логіном вже існує."


class OptimisticLockConflictException(ConflictException):
    """Виняток конфлікту оптимістичного блокування (OCC) за версією сутності."""

    status_code: int = 409
    default_error_code: str = "OPTIMISTIC_LOCK_CONFLICT"
    default_message: str = "Дані було змінено іншим процесом. Будь ласка, оновіть стан перед внесенням змін."


class DomainException(AppException):
    """Базовий клас доменних помилок та порушення бізнес-правил."""

    status_code: int = 400
    default_error_code: str = "DOMAIN_ERROR"
    default_message: str = "Порушення бізнес-правил предметної області."


class ValidationException(DomainException):
    """Виняток валідації вхідних даних або некоректного формату."""

    default_error_code: str = "VALIDATION_ERROR"
    default_message: str = "Помилка валідації даних."


class InactiveEntityError(DomainException):
    """Спроба виконання дій над деактивованою сутністю."""

    default_error_code: str = "ENTITY_INACTIVE"
    default_message: str = "Неможливо виконати операцію над деактивованим ресурсом. Спочатку відновіть його."


class IncompatibleScheduleLogicError(DomainException):
    """Виняток несумісності обраної логіки планування з типом нагадування."""

    default_error_code: str = "INCOMPATIBLE_SCHEDULE_LOGIC"
    default_message: str = "Обрана логіка планування несумісна з цим типом нагадування."


class InvalidDiscountCycleError(DomainException):
    """Виняток некоректних параметрів акційного циклу знижки підписки."""

    default_error_code: str = "INVALID_DISCOUNT_CYCLE"
    default_message: str = "Некоректні параметри акційного циклу знижки."


class UnauthorizedException(AppException):
    """Виняток відсутності або недійсності автентифікації."""

    status_code: int = 401
    default_error_code: str = "UNAUTHORIZED"
    default_message: str = "Потрібна автентифікація для доступу до ресурсу."


class InvalidCredentialsException(UnauthorizedException):
    """Виняток невірних облікових даних (логін або пароль)."""

    default_error_code: str = "INVALID_CREDENTIALS"
    default_message: str = "Неправильний логін або пароль."


class InvalidTokenException(UnauthorizedException):
    """Виняток недійсного, відкликаного або протермінованого токена."""

    default_error_code: str = "INVALID_TOKEN"
    default_message: str = "Токен недійсний або його термін дії закінчився."


class ForbiddenException(AppException):
    """Виняток недостатності прав доступу (RBAC)."""

    status_code: int = 403
    default_error_code: str = "FORBIDDEN"
    default_message: str = "У вас немає прав для виконання цієї дії."


class AccountDeactivatedException(ForbiddenException):
    """Виняток спроби входу або дії для деактивованого акаунта."""

    default_error_code: str = "ACCOUNT_DEACTIVATED"
    default_message: str = "Обліковий запис користувача деактивовано."


class ProtectedResourceException(ForbiddenException):
    """Виняток спроби зміни або видалення захищеного системного ресурсу (наприклад, SuperAdmin)."""

    default_error_code: str = "PROTECTED_RESOURCE"
    default_message: str = "Цей системний ресурс захищений від модифікації або видалення."


class ResourceLockedException(ConflictException):
    """Виняток, коли ресурс не може бути видалений через пов'язані дані."""

    default_error_code: str = "RESOURCE_LOCKED"
    default_message: str = "Неможливо остаточно видалити запис, оскільки він використовується в пов'язаних даних."


class ResourceAlreadyActiveException(ConflictException):
    """Виняток спроби відновити або активувати вже активний ресурс."""

    default_error_code: str = "RESOURCE_ALREADY_ACTIVE"
    default_message: str = "Цей ресурс вже є активним."


class ResourceAlreadyInactiveException(ConflictException):
    """Виняток спроби деактивувати вже неактивний ресурс."""

    default_error_code: str = "RESOURCE_ALREADY_INACTIVE"
    default_message: str = "Цей ресурс вже є неактивним."
