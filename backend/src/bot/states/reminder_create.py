from aiogram.fsm.state import State, StatesGroup


class OpenTaskCreateStates(StatesGroup):
    """Стани FSM-майстра створення відкритої справи (OPEN_TASK)."""

    waiting_for_title = State()
    waiting_for_times = State()


class AnniversaryCreateStates(StatesGroup):
    """Стани FSM-майстра створення річниці або свята (ANNIVERSARY)."""

    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_lead_times = State()


class DeadlineTaskCreateStates(StatesGroup):
    """Стани FSM-майстра створення задачі з дедлайном (DEADLINE_TASK)."""

    waiting_for_title = State()
    waiting_for_deadline = State()
    waiting_for_priority = State()


class SubscriptionCreateStates(StatesGroup):
    """Стани FSM-майстра створення підписки або регулярного платежу (SUBSCRIPTION)."""

    waiting_for_title = State()
    waiting_for_amount_currency = State()
    waiting_for_billing_day = State()
    waiting_for_mode = State()
    waiting_for_trial_date = State()
    waiting_for_discount_details = State()


class MedicationCreateStates(StatesGroup):
    """Стани FSM-майстра створення курсу прийому лікарського засобу (MEDICATION)."""

    waiting_for_title = State()
    waiting_for_schedule_mode = State()
    waiting_for_schedule_value = State()
    waiting_for_duration = State()
    waiting_for_strict_mode = State()
