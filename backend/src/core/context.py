from contextvars import ContextVar
from uuid import UUID

correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id_ctx", default=None)
current_user_id_ctx: ContextVar[UUID | None] = ContextVar("current_user_id_ctx", default=None)
current_username_ctx: ContextVar[str | None] = ContextVar("current_username_ctx", default=None)


def get_correlation_id() -> str | None:
    """Отримання поточного ідентифікатора кореляції (correlation_id) з контексту виконання."""
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Встановлення ідентифікатора кореляції для поточного асинхронного контексту."""
    correlation_id_ctx.set(correlation_id)


def get_current_user_id() -> UUID | None:
    """Отримання ідентифікатора поточного автентифікованого користувача з контексту виконання."""
    return current_user_id_ctx.get()


def set_current_user_id(user_id: UUID | None) -> None:
    """Встановлення ідентифікатора поточного автентифікованого користувача для контексту виконання."""
    current_user_id_ctx.set(user_id)


def get_current_username() -> str | None:
    """Отримання логіна поточного автентифікованого користувача з контексту виконання."""
    return current_username_ctx.get()


def set_current_username(username: str | None) -> None:
    """Встановлення логіна поточного автентифікованого користувача для контексту виконання."""
    current_username_ctx.set(username)
