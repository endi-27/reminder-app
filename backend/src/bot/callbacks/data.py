from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ReminderActionCallback(CallbackData, prefix="reminder"):
    """
    Фабрика callback_data для кнопок дій під сповіщеннями нагадувань.

    Формат у Telegram: reminder:{action}:{reminder_id}:{minutes}
    Для дій без відкладення часу параметр minutes дорівнює 0.
    """

    action: str
    reminder_id: UUID
    minutes: int = 0


class ReminderListFilterCallback(CallbackData, prefix="rem_list"):
    """
    Фабрика callback_data для фільтрації списку нагадувань та пагінації.

    Формат у Telegram: rem_list:{category}:{page}
    Категорія: ALL або значення ReminderType (ANNIVERSARY, OPEN_TASK тощо).
    """

    category: str = "ALL"
    page: int = 1


class ReminderDetailCallback(CallbackData, prefix="rem_det"):
    """
    Фабрика callback_data для взаємодії з карткою деталей нагадування.

    Формат у Telegram: rem_det:{action}:{reminder_id}
    Дії: view, pause, resume, delete, stats, done.
    """

    action: str
    reminder_id: UUID


class CreateReminderTypeCallback(CallbackData, prefix="rem_new"):
    """
    Фабрика callback_data для початкового вибору одного з 5 типів нагадування.

    Формат у Telegram: rem_new:{reminder_type}
    """

    reminder_type: str


class CreateWizardCallback(CallbackData, prefix="wiz", sep="#"):
    """
    Фабрика callback_data для швидких кнопок у покрокових FSM-майстрах створення.

    Формат у Telegram: wiz#{step}#{value}
    """

    step: str
    value: str


class SettingsCallback(CallbackData, prefix="cfg", sep="#"):
    """
    Фабрика callback_data для навігації та зміни користувацьких налаштувань.

    Формат у Telegram: cfg#{section}#{value}
    Розділи: menu, bank, quiet, tz, escalate.
    """

    section: str
    value: str = "none"
