from aiogram.fsm.state import State, StatesGroup


class SettingsEditStates(StatesGroup):
    """Стани скінченного автомата (FSM) для ручного редагування налаштувань."""

    waiting_for_custom_quiet_hours = State()
    waiting_for_custom_timezone = State()
