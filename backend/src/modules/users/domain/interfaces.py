from typing import Protocol
from uuid import UUID

from src.modules.users.domain.models import User, UserTelegramAccount


class IUserRepository(Protocol):
    """Порт репозиторію для збереження та завантаження агрегатів користувача."""

    async def get_by_id(self, entity_id: UUID) -> User | None:
        """Отримання агрегата користувача за первинним ключем UUIDv7."""
        ...

    async def get_by_username(self, username: str) -> User | None:
        """Пошук користувача за унікальним логіном."""
        ...

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Пошук користувача за ідентифікатором Telegram-акаунта."""
        ...

    async def exists_by_username(self, username: str) -> bool:
        """Перевірка наявності користувача з вказаним логіном."""
        ...

    async def exists_super_admin(self) -> bool:
        """Перевірка наявності хоча б одного користувача з роллю SUPER_ADMIN."""
        ...

    async def save(self, entity: User, /) -> None:
        """Збереження або оновлення агрегата користувача в базі даних."""
        ...

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        """Фізичне видалення (Hard Delete) користувача за ідентифікатором."""
        ...

    async def get_telegram_account_by_id(self, account_id: UUID) -> UserTelegramAccount | None:
        """Пошук профілю Telegram за його первинним ключем UUIDv7."""
        ...

    async def get_telegram_account_by_tg_id(self, telegram_id: int) -> UserTelegramAccount | None:
        """Пошук профілю Telegram за числовим ідентифікатором Telegram ID."""
        ...

    async def get_telegram_account_by_chat_id(self, chat_id: int) -> UserTelegramAccount | None:
        """Пошук профілю Telegram за числовим ідентифікатором Chat ID."""
        ...

    async def save_telegram_account(self, account: UserTelegramAccount, /) -> None:
        """Збереження або оновлення профілю Telegram."""
        ...

    async def delete_telegram_account_by_id(self, account_id: UUID, /) -> bool:
        """Фізичне видалення (Hard Delete) профілю Telegram."""
        ...
