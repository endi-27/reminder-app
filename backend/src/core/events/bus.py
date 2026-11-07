import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from src.core.events.base import BaseEvent
from src.core.logger import logger
from src.core.protocols import IEventBus

TEvent = TypeVar("TEvent", bound=BaseEvent)
EventHandler = Callable[[Any], Awaitable[None]]


class AsyncEventBus(IEventBus):
    """Асинхронна шина подій для внутрішньопроцесної доставки подій (In-Process EDA)."""

    def __init__(self) -> None:
        self._subscribers: dict[type[BaseEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[TEvent], handler: Callable[[TEvent], Awaitable[None]]) -> None:
        """Реєстрація слухача для типу події з дедуплікацією."""
        if handler in self._subscribers[event_type]:
            logger.debug(
                "Слухача {handler} вже зареєстровано на подію {event}, пропуск повторної реєстрації",
                handler=getattr(handler, "__name__", str(handler)),
                event=event_type.__name__,
            )
            return

        self._subscribers[event_type].append(handler)
        logger.debug(
            "Зареєстровано слухача {handler} на подію {event}",
            handler=getattr(handler, "__name__", str(handler)),
            event=event_type.__name__,
        )

    def on(
        self, event_type: type[TEvent]
    ) -> Callable[[Callable[[TEvent], Awaitable[None]]], Callable[[TEvent], Awaitable[None]]]:
        """Синтаксичний цукор: декоратор для реєстрації обробника події."""

        def decorator(handler: Callable[[TEvent], Awaitable[None]]) -> Callable[[TEvent], Awaitable[None]]:
            self.subscribe(event_type, handler)
            return handler

        return decorator

    def clear(self) -> None:
        """Очищення всіх зареєстрованих підписників (зокрема для ізоляції тестів)."""
        self._subscribers.clear()

    async def publish(self, *events: BaseEvent) -> None:
        """
        Публікація однієї або кількох подій усім зареєстрованим слухачам.
        Підтримує поліморфну доставку: обробник викликається, якщо тип події є підкласом зареєстрованого типу.
        """
        for event in events:
            event_cls = type(event)
            handlers: list[EventHandler] = []
            seen: set[EventHandler] = set()
            for registered_type, subscribers in self._subscribers.items():
                if issubclass(event_cls, registered_type):
                    for sub in subscribers:
                        if sub not in seen:
                            seen.add(sub)
                            handlers.append(sub)

            if not handlers:
                continue

            tasks = [self._safe_execute(handler, event) for handler in handlers]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_execute(self, handler: EventHandler, event: BaseEvent) -> None:
        """Безпечне виконання хендлера з перехопленням та детальним логуванням помилок."""
        try:
            await handler(event)
        except Exception as err:
            logger.opt(exception=err).error(
                "Помилка виконання хендлера {handler} для події {event_name} (entity_id={entity_id}): {err}",
                handler=getattr(handler, "__name__", str(handler)),
                event_name=event.event_name,
                entity_id=event.entity_id,
                err=str(err),
            )
