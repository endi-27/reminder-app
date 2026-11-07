from typing import Protocol
from uuid import UUID

from src.modules.users.domain.models import User


class IUserRepository(Protocol):
    """Порт репозиторію для збереження та завантаження агрегатів користувача."""

    async def get_by_id(self, entity_id: UUID, *, include_deleted: bool = False) -> User | None:
        """Отримання агрегата користувача за первинним ключем UUIDv7."""
        ...

    async def get_by_username(self, username: str, *, include_deleted: bool = False) -> User | None:
        """Пошук користувача за унікальним логіном."""
        ...

    async def get_by_telegram_id(self, telegram_id: int, *, include_deleted: bool = False) -> User | None:
        """Пошук користувача за ідентифікатором Telegram-акаунта."""
        ...

    async def exists_by_username(self, username: str) -> bool:
        """Перевірка наявності користувача з вказаним логіном."""
        ...

    async def save(self, entity: User, /) -> None:
        """Збереження або оновлення агрегата користувача в базі даних."""
        ...

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        """Фізичне видалення (Hard Delete) користувача за ідентифікатором."""
        ...
