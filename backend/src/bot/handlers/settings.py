import html
import re
from datetime import time
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.bot.callbacks.data import SettingsCallback
from src.bot.client.api_client import BackendApiClient
from src.bot.formatters.messages import format_settings_message
from src.bot.keyboards import (
    BTN_SETTINGS,
    build_bank_selection_keyboard,
    build_quiet_hours_keyboard,
    build_settings_main_keyboard,
    build_timezone_selection_keyboard,
)
from src.bot.states.settings_edit import SettingsEditStates
from src.modules.users.application.dto import UpdateUserSettingsCommand
from src.modules.users.domain.enums import ExchangeRateProvider
from src.modules.users.queries.dto import UserResponseDTO

settings_router = Router(name="settings")


async def _safe_edit_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Безпечне редагування тексту повідомлення з ігноруванням 'message is not modified'."""
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise


@settings_router.message(Command("settings"))
@settings_router.message(F.text == BTN_SETTINGS)
async def handle_settings(
    message: Message,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """
    Показ головного екрана налаштувань (команда /settings або кнопка '⚙️ Налаштування').

    Запитує актуальні налаштування користувача з контролем версії OCC та надсилає інлайн-меню.
    """
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (message.from_user.id if message.from_user else 0)
    )
    fresh_settings = await api_client.get_user_settings(telegram_id)
    text = format_settings_message(fresh_settings)
    await message.answer(text, reply_markup=build_settings_main_keyboard(fresh_settings))


@settings_router.callback_query(SettingsCallback.filter())
async def handle_settings_callback(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
    state: FSMContext,
) -> None:
    """
    Маршрутизатор інлайн-дій у меню налаштувань.

    Підтримує зміну банку, періоду тиші, часового поясу, автоескалації та повернення до головного меню.
    """
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (callback.from_user.id if callback.from_user else 0)
    )
    section = callback_data.section
    value = callback_data.value

    if section == "menu":
        await state.clear()
        fresh_settings = await api_client.get_user_settings(telegram_id)
        await _safe_edit_message(
            callback,
            format_settings_message(fresh_settings),
            build_settings_main_keyboard(fresh_settings),
        )
        await callback.answer()

    elif section == "bank":
        if value == "menu":
            fresh_settings = await api_client.get_user_settings(telegram_id)
            current_bank = (
                fresh_settings.preferred_bank.value
                if hasattr(fresh_settings.preferred_bank, "value")
                else str(fresh_settings.preferred_bank)
            )
            await _safe_edit_message(
                callback,
                "🏦 <b>Оберіть пріоритетний банк для розрахунку валютних підписок:</b>",
                build_bank_selection_keyboard(current_bank),
            )
            await callback.answer()
        else:
            fresh_settings = await api_client.get_user_settings(telegram_id)
            updated_settings = await api_client.update_user_settings(
                telegram_id,
                UpdateUserSettingsCommand(
                    version=fresh_settings.version,
                    preferred_bank=ExchangeRateProvider(value),
                ),
            )
            await _safe_edit_message(
                callback,
                format_settings_message(updated_settings),
                build_settings_main_keyboard(updated_settings),
            )
            await callback.answer("✅ Пріоритетний банк оновлено!")

    elif section == "escalate":
        fresh_settings = await api_client.get_user_settings(telegram_id)
        new_val = not fresh_settings.auto_deadline_priority_escalation
        updated_settings = await api_client.update_user_settings(
            telegram_id,
            UpdateUserSettingsCommand(
                version=fresh_settings.version,
                auto_deadline_priority_escalation=new_val,
            ),
        )
        await _safe_edit_message(
            callback,
            format_settings_message(updated_settings),
            build_settings_main_keyboard(updated_settings),
        )
        await callback.answer("✅ Налаштування автоескалації змінено!")

    elif section == "quiet":
        if value == "menu":
            await _safe_edit_message(
                callback,
                "🌙 <b>Оберіть вікно тихих годин:</b>",
                build_quiet_hours_keyboard(),
            )
            await callback.answer()
        elif value == "custom":
            await state.set_state(SettingsEditStates.waiting_for_custom_quiet_hours)
            await _safe_edit_message(
                callback,
                "⌨️ Введіть інтервал тихих годин у форматі <code>ГГ:ХХ-ГГ:ХХ</code> "
                "(наприклад, <code>23:00-08:00</code>):",
            )
            await callback.answer()
        else:
            start_str, end_str = value.split("-")
            start_time = time.fromisoformat(start_str)
            end_time = time.fromisoformat(end_str)
            fresh_settings = await api_client.get_user_settings(telegram_id)
            updated_settings = await api_client.update_user_settings(
                telegram_id,
                UpdateUserSettingsCommand(
                    version=fresh_settings.version,
                    quiet_hours_start=start_time,
                    quiet_hours_end=end_time,
                ),
            )
            await _safe_edit_message(
                callback,
                format_settings_message(updated_settings),
                build_settings_main_keyboard(updated_settings),
            )
            await callback.answer("✅ Тихі години оновлено!")

    elif section == "tz":
        if value == "menu":
            await _safe_edit_message(
                callback,
                "🌍 <b>Оберіть часовий пояс:</b>",
                build_timezone_selection_keyboard(),
            )
            await callback.answer()
        elif value == "custom":
            await state.set_state(SettingsEditStates.waiting_for_custom_timezone)
            await _safe_edit_message(
                callback,
                "⌨️ Введіть назву часового поясу у форматі IANA "
                "(наприклад, <code>Europe/Kyiv</code> або <code>America/New_York</code>):",
            )
            await callback.answer()
        else:
            ZoneInfo(value)
            fresh_settings = await api_client.get_user_settings(telegram_id)
            updated_settings = await api_client.update_user_settings(
                telegram_id,
                UpdateUserSettingsCommand(
                    version=fresh_settings.version,
                    timezone=value,
                ),
            )
            await _safe_edit_message(
                callback,
                format_settings_message(updated_settings),
                build_settings_main_keyboard(updated_settings),
            )
            await callback.answer("✅ Часовий пояс оновлено!")


@settings_router.message(SettingsEditStates.waiting_for_custom_quiet_hours)
async def handle_custom_quiet_hours_input(
    message: Message,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
    state: FSMContext,
) -> None:
    """Обробка текстового введення користувацького інтервалу тихих годин."""
    raw_text = (message.text or "").strip()
    match = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)-([01]?\d|2[0-3]):([0-5]\d)$", raw_text)
    if not match:
        await message.answer(
            "⚠️ Некоректний формат часу. Введіть інтервал у форматі <code>ГГ:ХХ-ГГ:ХХ</code> "
            "(наприклад, <code>23:00-08:00</code>):"
        )
        return

    s_hour, s_min, e_hour, e_min = map(int, match.groups())
    start_time = time(s_hour, s_min)
    end_time = time(e_hour, e_min)

    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (message.from_user.id if message.from_user else 0)
    )
    fresh_settings = await api_client.get_user_settings(telegram_id)
    updated_settings = await api_client.update_user_settings(
        telegram_id,
        UpdateUserSettingsCommand(
            version=fresh_settings.version,
            quiet_hours_start=start_time,
            quiet_hours_end=end_time,
        ),
    )
    await state.clear()
    time_range = f"{start_time.strftime('%H:%M')} – {end_time.strftime('%H:%M')}"
    await message.answer(
        f"✅ Тихі години успішно встановлено на <code>{time_range}</code>!\n\n"
        + format_settings_message(updated_settings),
        reply_markup=build_settings_main_keyboard(updated_settings),
    )


@settings_router.message(SettingsEditStates.waiting_for_custom_timezone)
async def handle_custom_timezone_input(
    message: Message,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
    state: FSMContext,
) -> None:
    """Обробка текстового введення назви часового поясу IANA."""
    tz_candidate = (message.text or "").strip()
    try:
        ZoneInfo(tz_candidate)
    except Exception:
        await message.answer(
            "⚠️ Невідомий або некоректний часовий пояс. Будь ласка, введіть валідну IANA назву "
            "(наприклад, <code>Europe/Kyiv</code> або <code>America/New_York</code>):"
        )
        return

    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (message.from_user.id if message.from_user else 0)
    )
    fresh_settings = await api_client.get_user_settings(telegram_id)
    updated_settings = await api_client.update_user_settings(
        telegram_id,
        UpdateUserSettingsCommand(
            version=fresh_settings.version,
            timezone=tz_candidate,
        ),
    )
    await state.clear()
    await message.answer(
        f"✅ Часовий пояс успішно оновлено на <code>{html.escape(tz_candidate)}</code>!\n\n"
        + format_settings_message(updated_settings),
        reply_markup=build_settings_main_keyboard(updated_settings),
    )
