from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.client.api_client import BackendApiClient
from src.bot.formatters.messages import format_rates_message
from src.bot.keyboards import BTN_RATES
from src.modules.users.queries.dto import UserResponseDTO

finance_router = Router(name="finance")


@finance_router.message(Command("rates"))
@finance_router.message(F.text == BTN_RATES)
async def handle_rates(
    message: Message,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """
    Обробник перегляду курсів валют (команда /rates або кнопка '💱 Курси валют').

    Запитує актуальні курси НБУ, Monobank та ПриватБанку через API бекенду
    і форматує їх у наочну таблицю з виділенням пріоритетного банку користувача.
    """
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (message.from_user.id if message.from_user else 0)
    )
    rates = await api_client.get_latest_rates(telegram_id=telegram_id)
    preferred_bank = (
        current_user.settings.preferred_bank.value
        if hasattr(current_user.settings.preferred_bank, "value")
        else str(current_user.settings.preferred_bank)
    )
    rates_text = format_rates_message(rates, preferred_bank=preferred_bank)
    await message.answer(rates_text)
