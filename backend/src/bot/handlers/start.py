from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot.formatters.messages import format_help_message, format_welcome_message
from src.bot.keyboards import BTN_CANCEL, build_main_reply_keyboard
from src.modules.users.queries.dto import UserResponseDTO

start_router = Router(name="start")


@start_router.message(Command("cancel"), StateFilter("*"))
@start_router.message(F.text == BTN_CANCEL, StateFilter("*"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    """
    Глобальне скасування поточної дії або активного діалогу FSM.

    Очищає стан скінченного автомата та повертає головне Reply-меню.
    """
    await state.clear()
    await message.answer(
        "❌ Поточну дію скасовано.",
        reply_markup=build_main_reply_keyboard(),
    )


@start_router.message(CommandStart(), StateFilter("*"))
async def handle_start(
    message: Message,
    current_user: UserResponseDTO,
    state: FSMContext,
) -> None:
    """
    Обробник команди /start.

    Скидає будь-який активний стан FSM, надсилає персональне привітання
    та відображає головну клавіатуру дій.
    """
    await state.clear()
    welcome_text = format_welcome_message(current_user)
    await message.answer(
        welcome_text,
        reply_markup=build_main_reply_keyboard(),
    )


@start_router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """
    Обробник команди /help.

    Надсилає структуровану довідку щодо всіх доступних команд та 5 типів нагадувань.
    """
    help_text = format_help_message()
    await message.answer(
        help_text,
        reply_markup=build_main_reply_keyboard(),
    )
