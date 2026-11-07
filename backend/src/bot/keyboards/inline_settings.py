from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.data import SettingsCallback
from src.modules.users.queries.dto import UserSettingsResponseDTO


def build_settings_main_keyboard(settings: UserSettingsResponseDTO) -> InlineKeyboardMarkup:
    """Генерація головного інлайн-меню налаштувань користувача."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🏦 Змінити пріоритетний банк",
        callback_data=SettingsCallback(section="bank", value="menu"),
    )
    builder.button(
        text="🌙 Змінити тихі години",
        callback_data=SettingsCallback(section="quiet", value="menu"),
    )
    builder.button(
        text="🌍 Змінити часовий пояс",
        callback_data=SettingsCallback(section="tz", value="menu"),
    )
    escalate_status = "Увімкнено ✅" if settings.auto_deadline_priority_escalation else "Вимкнено ❌"
    builder.button(
        text=f"📈 Автоескалація: {escalate_status}",
        callback_data=SettingsCallback(section="escalate", value="toggle"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_bank_selection_keyboard(current_bank: str) -> InlineKeyboardMarkup:
    """Вибір пріоритетного банку для отримання курсів валют."""
    builder = InlineKeyboardBuilder()
    banks = [
        ("NBU", "НБУ (Офіційний)"),
        ("MONOBANK", "Monobank (Картковий)"),
        ("PRIVATBANK", "ПриватБанк (Картковий)"),
    ]
    for code, title in banks:
        prefix = "✅ " if code.upper() == current_bank.upper() else ""
        builder.button(
            text=f"{prefix}{title}",
            callback_data=SettingsCallback(section="bank", value=code),
        )
    builder.button(
        text="⬅️ Назад",
        callback_data=SettingsCallback(section="menu", value="main"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_quiet_hours_keyboard() -> InlineKeyboardMarkup:
    """Вибір пресетів нічних тихих годин або введення власного діапазону."""
    builder = InlineKeyboardBuilder()
    presets = [
        ("23:00 – 08:00", "23:00-08:00"),
        ("22:00 – 07:00", "22:00-07:00"),
        ("00:00 – 08:00", "00:00-08:00"),
        ("⌨️ Ввести власний час", "custom"),
    ]
    for text, value in presets:
        builder.button(text=text, callback_data=SettingsCallback(section="quiet", value=value))
    builder.button(
        text="⬅️ Назад",
        callback_data=SettingsCallback(section="menu", value="main"),
    )
    builder.adjust(1)
    return builder.as_markup()


def build_timezone_selection_keyboard() -> InlineKeyboardMarkup:
    """Вибір часового поясу користувача з популярних або введення вручну."""
    builder = InlineKeyboardBuilder()
    timezones = [
        ("🇺🇦 Europe/Kyiv", "Europe/Kyiv"),
        ("🇵🇱 Europe/Warsaw", "Europe/Warsaw"),
        ("🇩🇪 Europe/Berlin", "Europe/Berlin"),
        ("🌐 UTC", "UTC"),
        ("⌨️ Ввести вручну", "custom"),
    ]
    for text, value in timezones:
        builder.button(text=text, callback_data=SettingsCallback(section="tz", value=value))
    builder.button(
        text="⬅️ Назад",
        callback_data=SettingsCallback(section="menu", value="main"),
    )
    builder.adjust(1)
    return builder.as_markup()
