from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.data import ReminderDetailCallback, ReminderListFilterCallback
from src.bot.client.api_client import BackendApiClient
from src.bot.formatters.messages import (
    format_medication_stats_message,
    format_reminder_detail_message,
    format_reminders_list_message,
)
from src.bot.keyboards import (
    BTN_MY_REMINDERS,
    build_reminder_detail_keyboard,
    build_reminders_list_keyboard,
)
from src.modules.reminders.application.dto import ReminderActionCommand, ReminderActionType
from src.modules.reminders.domain.enums import ReminderType
from src.modules.users.queries.dto import UserResponseDTO

reminders_list_router = Router(name="reminders_list")


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


@reminders_list_router.message(Command("list"))
@reminders_list_router.message(F.text == BTN_MY_REMINDERS)
async def handle_list_reminders(
    message: Message,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """
    Показ першої сторінки списку всіх нагадувань користувача.

    Обробляє команду /list або кнопку '📋 Мої нагадування'.
    """
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (message.from_user.id if message.from_user else 0)
    )
    user_tz = current_user.settings.timezone
    page_data = await api_client.list_reminders(telegram_id, page=1, size=5)
    text = format_reminders_list_message(page_data, category="ALL", user_timezone=user_tz)
    await message.answer(text, reply_markup=build_reminders_list_keyboard(page_data, category="ALL"))


@reminders_list_router.callback_query(ReminderListFilterCallback.filter())
async def handle_list_filter_callback(
    callback: CallbackQuery,
    callback_data: ReminderListFilterCallback,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """
    Обробка пагінації та фільтрації нагадувань за типами (інлайн-кнопки фільтрів).
    """
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (callback.from_user.id if callback.from_user else 0)
    )
    user_tz = current_user.settings.timezone
    category = callback_data.category
    page = max(1, callback_data.page)

    rem_type: ReminderType | None = None
    if category != "ALL":
        rem_type = ReminderType(category)

    page_data = await api_client.list_reminders(
        telegram_id,
        page=page,
        size=5,
        reminder_type=rem_type,
    )
    text = format_reminders_list_message(page_data, category=category, user_timezone=user_tz)
    await _safe_edit_message(
        callback,
        text,
        build_reminders_list_keyboard(page_data, category=category),
    )
    await callback.answer()


@reminders_list_router.callback_query(ReminderDetailCallback.filter())
async def handle_reminder_detail_callback(
    callback: CallbackQuery,
    callback_data: ReminderDetailCallback,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """
    Обробка взаємодії з карткою нагадування: перегляд, завершення, пауза, відновлення, видалення та статистика.
    """
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (callback.from_user.id if callback.from_user else 0)
    )
    user_tz = current_user.settings.timezone
    action = callback_data.action
    rem_id = callback_data.reminder_id

    if action == "view":
        reminder = await api_client.get_reminder(telegram_id, rem_id)
        card_text = format_reminder_detail_message(reminder, user_tz)
        await _safe_edit_message(
            callback,
            card_text,
            build_reminder_detail_keyboard(reminder),
        )
        await callback.answer()

    elif action == "done":
        cmd = ReminderActionCommand(action=ReminderActionType.COMPLETE)
        reminder = await api_client.perform_reminder_action(telegram_id, rem_id, cmd)
        card_text = format_reminder_detail_message(reminder, user_tz)
        await _safe_edit_message(
            callback,
            card_text,
            build_reminder_detail_keyboard(reminder),
        )
        await callback.answer("✅ Позначено як виконане!")

    elif action == "pause":
        cmd = ReminderActionCommand(action=ReminderActionType.PAUSE)
        reminder = await api_client.perform_reminder_action(telegram_id, rem_id, cmd)
        card_text = format_reminder_detail_message(reminder, user_tz)
        await _safe_edit_message(
            callback,
            card_text,
            build_reminder_detail_keyboard(reminder),
        )
        await callback.answer("⏸ Нагадування призупинено")

    elif action == "resume":
        cmd = ReminderActionCommand(action=ReminderActionType.RESUME)
        reminder = await api_client.perform_reminder_action(telegram_id, rem_id, cmd)
        card_text = format_reminder_detail_message(reminder, user_tz)
        await _safe_edit_message(
            callback,
            card_text,
            build_reminder_detail_keyboard(reminder),
        )
        await callback.answer("▶️ Нагадування відновлено")

    elif action == "stats":
        reminder = await api_client.get_reminder(telegram_id, rem_id)
        stats = await api_client.get_medication_logs(telegram_id, rem_id)
        stats_text = format_medication_stats_message(reminder, stats, user_tz)
        builder = InlineKeyboardBuilder()
        builder.button(
            text="⬅️ Назад до нагадування",
            callback_data=ReminderDetailCallback(action="view", reminder_id=reminder.id),
        )
        await _safe_edit_message(callback, stats_text, builder.as_markup())
        await callback.answer()

    elif action == "delete":
        await api_client.delete_reminder(telegram_id, rem_id, hard=False)
        page_data = await api_client.list_reminders(telegram_id, page=1, size=5)
        text = format_reminders_list_message(page_data, category="ALL", user_timezone=user_tz)
        await _safe_edit_message(
            callback,
            text,
            build_reminders_list_keyboard(page_data, category="ALL"),
        )
        await callback.answer("🗑 Нагадування видалено")
    else:
        await callback.answer()
