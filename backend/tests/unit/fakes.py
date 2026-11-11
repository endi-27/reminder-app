from types import TracebackType
from typing import Any

from src.core import (
    IEventBus,
    INotificationPublisher,
    IPasswordHasher,
    IUnitOfWork,
)


class FakeUnitOfWork(IUnitOfWork):
    """Швидкий тестовий дублер Unit of Work для юніт-тестів без БД (< 0.05 сек)."""

    def __init__(self) -> None:
        self.committed: bool = False
        self.commit_count: int = 0
        self.rolled_back: bool = False
        self.in_context: bool = False
        self.fail_on_commit: bool = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        self.in_context = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.in_context = False
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError("Симуляція помилки збереження транзакції в БД.")
        self.committed = True
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeEventBus(IEventBus):
    """Тестовий дублер шини подій із фіксацією опублікованих подій."""

    def __init__(self) -> None:
        self.published_events: list[Any] = []

    async def publish(self, *events: Any) -> None:
        self.published_events.extend(events)

    def has_event_of_type(self, event_type: type) -> bool:
        return any(isinstance(e, event_type) for e in self.published_events)

    def get_events_of_type(self, event_type: type) -> list[Any]:
        return [e for e in self.published_events if isinstance(e, event_type)]


class FakePasswordHasher(IPasswordHasher):
    """Швидкий тестовий дублер сервісу хешування паролів (< 0.001 сек)."""

    def __init__(self) -> None:
        self.dummy_verify_call_count = 0

    def hash(self, password: str, rounds: int | None = None) -> str:
        return f"hashed_{password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        if hashed_password.startswith("hashed_"):
            return hashed_password == f"hashed_{plain_password}"
        return plain_password == hashed_password

    def dummy_verify(self, plain_password: str) -> bool:
        self.dummy_verify_call_count += 1
        return False


class FakeNotificationPublisher(INotificationPublisher):
    """Тестовий дублер сервісу публікації сповіщень у чергу доставки."""

    def __init__(self) -> None:
        self.published_payloads: list[Any] = []

    async def publish(self, payload: Any) -> None:
        self.published_payloads.append(payload)

    async def publish_many(self, payloads: Any) -> int:
        self.published_payloads.extend(payloads)
        return len(payloads)

    def count(self) -> int:
        return len(self.published_payloads)

    def clear(self) -> None:
        self.published_payloads.clear()
