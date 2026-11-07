from aiogram import Dispatcher

from src.bot.handlers.errors import errors_router
from src.bot.handlers.finance import finance_router
from src.bot.handlers.reminders_actions import reminders_actions_router
from src.bot.handlers.reminders_create import reminders_create_router
from src.bot.handlers.reminders_list import reminders_list_router
from src.bot.handlers.settings import settings_router
from src.bot.handlers.start import start_router


def setup_routers(dp: Dispatcher) -> None:
    """Реєструє всі дочірні модульні роутери у головному диспетчері бота в канонічному порядку."""
    routers = (
        errors_router,
        start_router,
        reminders_create_router,
        reminders_list_router,
        reminders_actions_router,
        finance_router,
        settings_router,
    )
    for router in routers:
        router._parent_router = None
    dp.include_routers(*routers)


__all__ = [
    "errors_router",
    "finance_router",
    "reminders_actions_router",
    "reminders_create_router",
    "reminders_list_router",
    "settings_router",
    "setup_routers",
    "start_router",
]
