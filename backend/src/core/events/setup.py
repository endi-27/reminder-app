from collections.abc import Callable

from src.core.events.bus import AsyncEventBus

_event_bus: AsyncEventBus | None = None
_subscribers_setup_fns: list[Callable[[AsyncEventBus], None]] = []


def get_event_bus() -> AsyncEventBus:
    """Отримання синглтона шини подій."""
    global _event_bus
    if _event_bus is None:
        _event_bus = AsyncEventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Скидання синглтона шини подій та списку налаштувань (зокрема для ізоляції тестів)."""
    global _event_bus, _subscribers_setup_fns
    if _event_bus is not None:
        _event_bus.clear()
    _event_bus = None
    _subscribers_setup_fns.clear()


def register_subscribers_setup(fn: Callable[[AsyncEventBus], None]) -> None:
    """Реєстрація модульної функції налаштування слухачів подій."""
    if fn not in _subscribers_setup_fns:
        _subscribers_setup_fns.append(fn)


def setup_event_bus() -> AsyncEventBus:
    """Ініціалізація зареєстрованих хуків слухачів шини подій."""
    bus = get_event_bus()
    for setup_fn in _subscribers_setup_fns:
        setup_fn(bus)
    return bus
