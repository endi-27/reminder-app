from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

BTN_CREATE_REMINDER = "➕ Створити нагадування"
BTN_MY_REMINDERS = "📋 Мої нагадування"
BTN_RATES = "💱 Курси валют"
BTN_SETTINGS = "⚙️ Налаштування"
BTN_CANCEL = "❌ Скасувати"


def build_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Генерація постійного головного меню бота (розкладка 2x2)."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN_CREATE_REMINDER)
    builder.button(text=BTN_MY_REMINDERS)
    builder.button(text=BTN_RATES)
    builder.button(text=BTN_SETTINGS)
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def build_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    """Генерація клавіатури скасування поточного FSM-діалогу."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN_CANCEL)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)
