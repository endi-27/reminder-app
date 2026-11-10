from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, ReplyKeyboardMarkup, User
from uuid6 import uuid7

from src.bot.callbacks.data import CreateReminderTypeCallback, CreateWizardCallback
from src.bot.client.api_client import BackendApiClient
from src.bot.handlers import setup_routers
from src.bot.handlers.reminders_create import (
    handle_anniversary_date,
    handle_anniversary_leads_callback,
    handle_anniversary_leads_message,
    handle_anniversary_title,
    handle_deadline_date_callback,
    handle_deadline_date_message,
    handle_deadline_priority_callback,
    handle_deadline_title,
    handle_medication_duration_callback,
    handle_medication_duration_message,
    handle_medication_schedule_mode,
    handle_medication_schedule_value,
    handle_medication_strict_callback,
    handle_medication_title,
    handle_new_reminder,
    handle_open_task_times_callback,
    handle_open_task_times_message,
    handle_open_task_title,
    handle_reminder_type_selection,
    handle_subscription_amount_currency,
    handle_subscription_billing_callback,
    handle_subscription_billing_message,
    handle_subscription_discount_details,
    handle_subscription_mode_callback,
    handle_subscription_title,
    handle_subscription_trial_date,
    reminders_create_router,
)
from src.bot.keyboards import (
    BTN_CANCEL,
    BTN_CREATE_REMINDER,
)
from src.bot.states.reminder_create import (
    AnniversaryCreateStates,
    DeadlineTaskCreateStates,
    MedicationCreateStates,
    OpenTaskCreateStates,
    SubscriptionCreateStates,
)
from src.modules.reminders.application.dto import CreateReminderCommand
from src.modules.reminders.domain.enums import (
    CurrencyCode,
    Priority,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.queries.dto import ReminderResponseDTO
from src.modules.users.domain.enums import ExchangeRateProvider, UserRole
from src.modules.users.queries.dto import (
    TelegramAccountResponseDTO,
    UserResponseDTO,
    UserSettingsResponseDTO,
)


class MockFSMContext:
    """Мок FSMContext для збереження внутрішнього стану та даних під час тестів."""

    def __init__(self, initial_data: dict[str, Any] | None = None, initial_state: Any = None) -> None:
        self.data: dict[str, Any] = dict(initial_data or {})
        self.current_state: Any = initial_state
        self.clear_called: bool = False

    async def get_data(self) -> dict[str, Any]:
        return dict(self.data)

    async def update_data(self, **kwargs: Any) -> dict[str, Any]:
        self.data.update(kwargs)
        return dict(self.data)

    async def set_state(self, state: Any = None) -> None:
        self.current_state = state

    async def clear(self) -> None:
        self.data.clear()
        self.current_state = None
        self.clear_called = True


def _make_dummy_user(
    user_id: UUID | None = None,
    tg_id: int = 123456789,
    timezone: str = "Europe/Kyiv",
) -> UserResponseDTO:
    uid = user_id or uuid7()
    return UserResponseDTO(
        id=uid,
        username="test_creator",
        role=UserRole.USER,
        telegram_account=TelegramAccountResponseDTO(
            id=uuid7(),
            telegram_id=tg_id,
            telegram_chat_id=tg_id,
            tg_username="creator_tg",
            tg_full_name="Створювач Нагадувань",
            version=1,
        ),
        settings=UserSettingsResponseDTO(
            id=uuid7(),
            user_id=uid,
            timezone=timezone,
            quiet_hours_start=time(23, 0),
            quiet_hours_end=time(8, 0),
            preferred_bank=ExchangeRateProvider.MONOBANK,
            auto_deadline_priority_escalation=True,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_dummy_reminder(
    reminder_type: ReminderType,
    schedule_logic: ScheduleLogicType,
    title: str = "Тестове нагадування",
    schedule_config: dict[str, Any] | None = None,
    lead_times: list[str] | None = None,
    regular_amount: Decimal | None = None,
    currency: CurrencyCode | None = None,
    due_datetime: datetime | None = None,
    is_trial: bool = False,
    trial_end_date: date | None = None,
    course_duration_days: int | None = None,
    strict_schedule: bool = False,
) -> ReminderResponseDTO:
    rid = uuid7()
    uid = uuid7()
    return ReminderResponseDTO(
        id=rid,
        user_id=uid,
        reminder_type=reminder_type,
        schedule_logic=schedule_logic,
        title=title,
        description=None,
        status=ReminderStatus.ACTIVE,
        next_trigger_at=datetime.now(UTC) + timedelta(hours=1),
        schedule_config=schedule_config or {},
        lead_times=lead_times or [],
        regular_amount=regular_amount,
        currency=currency,
        due_datetime=due_datetime,
        is_trial=is_trial,
        trial_end_date=trial_end_date,
        course_duration_days=course_duration_days,
        strict_schedule=strict_schedule,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        version=1,
    )


def _create_mock_message(
    text: str = "",
    tg_id: int = 123456789,
    bot: AsyncMock | None = None,
) -> tuple[Message, AsyncMock]:
    bot_mock = bot or AsyncMock(spec=Bot)
    user = User(id=tg_id, is_bot=False, first_name="Тест")
    chat = Chat(id=tg_id, type="private")
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text=text,
    ).as_(bot_mock)
    return msg, bot_mock


def _create_mock_callback(
    data: str,
    tg_id: int = 123456789,
    message_text: str = "Виберіть опцію",
    bot: AsyncMock | None = None,
) -> tuple[CallbackQuery, AsyncMock]:
    bot_mock = bot or AsyncMock(spec=Bot)
    user = User(id=tg_id, is_bot=False, first_name="Тест")
    chat = Chat(id=tg_id, type="private")
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text=message_text,
    ).as_(bot_mock)

    cb = CallbackQuery(
        id="cb_test",
        from_user=user,
        chat_instance="ci_test",
        data=data,
        message=msg,
    ).as_(bot_mock)
    return cb, bot_mock


def _get_sent_messages(bot: AsyncMock) -> list[SendMessage]:
    return [c[0][0] for c in bot.call_args_list if isinstance(c[0][0], SendMessage)]


def _get_callback_answers(bot: AsyncMock) -> list[AnswerCallbackQuery]:
    return [c[0][0] for c in bot.call_args_list if isinstance(c[0][0], AnswerCallbackQuery)]


# =============================================================================
# Тести точки входу та роутерів
# =============================================================================


@pytest.mark.asyncio
async def test_handle_new_reminder_command() -> None:
    msg, bot = _create_mock_message("/new")
    state = MockFSMContext(initial_data={"foo": "bar"}, initial_state="some_state")

    await handle_new_reminder(msg, state)

    assert state.clear_called is True
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Оберіть тип нагадування" in sent[0].text
    assert sent[0].reply_markup is not None


@pytest.mark.asyncio
async def test_handle_new_reminder_button() -> None:
    msg, bot = _create_mock_message(BTN_CREATE_REMINDER)
    state = MockFSMContext()

    await handle_new_reminder(msg, state)

    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Оберіть тип нагадування" in sent[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reminder_type, expected_state",
    [
        (ReminderType.OPEN_TASK, OpenTaskCreateStates.waiting_for_title),
        (ReminderType.ANNIVERSARY, AnniversaryCreateStates.waiting_for_title),
        (ReminderType.DEADLINE_TASK, DeadlineTaskCreateStates.waiting_for_title),
        (ReminderType.SUBSCRIPTION, SubscriptionCreateStates.waiting_for_title),
        (ReminderType.MEDICATION, MedicationCreateStates.waiting_for_title),
    ],
)
async def test_handle_reminder_type_selection(
    reminder_type: ReminderType,
    expected_state: Any,
) -> None:
    cb, bot = _create_mock_callback(f"rem_new:{reminder_type.value}")
    cb_data = CreateReminderTypeCallback(reminder_type=reminder_type.value)
    state = MockFSMContext()

    await handle_reminder_type_selection(cb, cb_data, state)

    assert state.current_state == expected_state
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert sent[0].reply_markup is not None
    assert isinstance(sent[0].reply_markup, ReplyKeyboardMarkup)
    # Перевіряємо наявність кнопки Скасувати в розмітці
    assert any(btn.text == BTN_CANCEL for row in sent[0].reply_markup.keyboard for btn in row)
    assert len(_get_callback_answers(bot)) == 1


# =============================================================================
# Тести майстра OPEN_TASK
# =============================================================================


@pytest.mark.asyncio
async def test_open_task_wizard_flow_via_callback() -> None:
    # 1. Введення назви
    msg, bot = _create_mock_message("Купити корм коту")
    state = MockFSMContext()

    await handle_open_task_title(msg, state)

    assert state.data["title"] == "Купити корм коту"
    assert state.current_state == OpenTaskCreateStates.waiting_for_times
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Оберіть графік щоденних нагадувань" in sent[0].text

    # 2. Вибір годин через інлайн-кнопку
    cb, bot2 = _create_mock_callback("wiz#open_times#09:00,14:00,19:00")
    cb_data = CreateWizardCallback(step="open_times", value="09:00,14:00,19:00")
    current_user = _make_dummy_user()

    created_dto = _make_dummy_reminder(
        reminder_type=ReminderType.OPEN_TASK,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title="Купити корм коту",
    )
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = created_dto

    await handle_open_task_times_callback(cb, cb_data, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    call_args = api_client.create_reminder.await_args
    assert current_user.telegram_account is not None
    assert call_args[0][0] == current_user.telegram_account.telegram_id
    cmd: CreateReminderCommand = call_args[0][1]
    assert cmd.reminder_type == ReminderType.OPEN_TASK
    assert cmd.schedule_logic == ScheduleLogicType.DAILY_AT_TIMES
    assert cmd.title == "Купити корм коту"
    assert cmd.schedule_config["times"] == ["09:00:00", "14:00:00", "19:00:00"]
    assert cmd.lead_times == []

    assert state.clear_called is True
    sent2 = _get_sent_messages(bot2)
    assert len(sent2) == 1
    assert "Відкриту справу створено" in sent2[0].text


@pytest.mark.asyncio
async def test_open_task_wizard_flow_via_message() -> None:
    msg, bot = _create_mock_message("08:30, 16:45")
    state = MockFSMContext(initial_data={"title": "Зателефонувати клієнту"})
    current_user = _make_dummy_user()

    created_dto = _make_dummy_reminder(
        reminder_type=ReminderType.OPEN_TASK,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title="Зателефонувати клієнту",
    )
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = created_dto

    await handle_open_task_times_message(msg, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.schedule_config["times"] == ["08:30:00", "16:45:00"]
    assert state.clear_called is True


@pytest.mark.asyncio
async def test_open_task_invalid_title_and_times() -> None:
    # Занадто довга назва (> 255)
    msg, bot = _create_mock_message("A" * 260)
    state = MockFSMContext()
    await handle_open_task_title(msg, state)
    assert "від 1 до 255" in _get_sent_messages(bot)[0].text
    assert state.current_state is None

    # Некоректні години
    msg2, bot2 = _create_mock_message("invalid_time")
    state2 = MockFSMContext(initial_data={"title": "Test"})
    api_client = AsyncMock(spec=BackendApiClient)
    await handle_open_task_times_message(msg2, state2, _make_dummy_user(), api_client)
    assert "Некоректний формат годин" in _get_sent_messages(bot2)[0].text
    api_client.create_reminder.assert_not_called()


# =============================================================================
# Тести майстра ANNIVERSARY
# =============================================================================


@pytest.mark.asyncio
async def test_anniversary_wizard_flow() -> None:
    # 1. Назва
    msg1, bot1 = _create_mock_message("День народження мами")
    state = MockFSMContext()
    await handle_anniversary_title(msg1, state)
    assert state.data["title"] == "День народження мами"
    assert state.current_state == AnniversaryCreateStates.waiting_for_date

    # 2. Дата з роком народження
    msg2, bot2 = _create_mock_message("15.05.1975")
    await handle_anniversary_date(msg2, state)
    assert state.data["day"] == 15
    assert state.data["month"] == 5
    assert state.data["birth_year"] == 1975
    assert state.current_state == AnniversaryCreateStates.waiting_for_lead_times

    # 3. Вибір завчасних сповіщень через callback
    cb, bot3 = _create_mock_callback("wiz#anniv_leads#14d,7d,3d,1d,0d")
    cb_data = CreateWizardCallback(step="anniv_leads", value="14d,7d,3d,1d,0d")
    current_user = _make_dummy_user()
    created_dto = _make_dummy_reminder(
        reminder_type=ReminderType.ANNIVERSARY,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title="День народження мами",
    )
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = created_dto

    await handle_anniversary_leads_callback(cb, cb_data, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.reminder_type == ReminderType.ANNIVERSARY
    assert cmd.schedule_logic == ScheduleLogicType.DATE_WITH_MONTH_INTERVAL
    assert cmd.schedule_config["day"] == 15
    assert cmd.schedule_config["month"] == 5
    assert cmd.schedule_config["birth_year"] == 1975
    assert cmd.schedule_config["interval_months"] == 12
    assert cmd.lead_times == ["14d", "7d", "3d", "1d", "0d"]
    assert state.clear_called is True


@pytest.mark.asyncio
async def test_anniversary_manual_leads_message() -> None:
    msg, bot = _create_mock_message("7d, 1d, 0d")
    state = MockFSMContext(initial_data={"title": "Річниця весілля", "day": 10, "month": 8, "birth_year": None})
    current_user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = _make_dummy_reminder(
        reminder_type=ReminderType.ANNIVERSARY,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title="Річниця весілля",
    )

    await handle_anniversary_leads_message(msg, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.lead_times == ["7d", "1d", "0d"]
    assert cmd.schedule_config["birth_year"] is None
    assert state.clear_called is True


@pytest.mark.asyncio
async def test_anniversary_invalid_date_and_leads() -> None:
    state = MockFSMContext(initial_data={"title": "Річниця"})
    # Невалідна дата (31 лютого)
    msg, bot = _create_mock_message("31.02.2024")
    await handle_anniversary_date(msg, state)
    assert "Некоректний формат дати" in _get_sent_messages(bot)[0].text

    # Невалідні інтервали
    msg2, bot2 = _create_mock_message("foo, bar")
    api_client = AsyncMock(spec=BackendApiClient)
    await handle_anniversary_leads_message(msg2, state, _make_dummy_user(), api_client)
    assert "Некоректний формат завчасних" in _get_sent_messages(bot2)[0].text
    api_client.create_reminder.assert_not_called()


# =============================================================================
# Тести майстра DEADLINE_TASK
# =============================================================================


@pytest.mark.asyncio
async def test_deadline_wizard_flow_quick_choice() -> None:
    # 1. Назва
    msg1, _ = _create_mock_message("Підготувати презентацію")
    state = MockFSMContext()
    await handle_deadline_title(msg1, state)
    assert state.data["title"] == "Підготувати презентацію"
    assert state.current_state == DeadlineTaskCreateStates.waiting_for_deadline

    # 2. Швидкий вибір дати (tomorrow_18)
    cb1, bot1 = _create_mock_callback("wiz#dl_date#tomorrow_18")
    cb_data1 = CreateWizardCallback(step="dl_date", value="tomorrow_18")
    current_user = _make_dummy_user(timezone="Europe/Kyiv")

    await handle_deadline_date_callback(cb1, cb_data1, state, current_user)

    assert "due_datetime_iso" in state.data
    assert state.current_state == DeadlineTaskCreateStates.waiting_for_priority
    assert "Оберіть пріоритет" in _get_sent_messages(bot1)[0].text

    # 3. Вибір пріоритету "AUTO"
    cb2, bot2 = _create_mock_callback("wiz#dl_prio#AUTO")
    cb_data2 = CreateWizardCallback(step="dl_prio", value="AUTO")
    created_dto = _make_dummy_reminder(
        reminder_type=ReminderType.DEADLINE_TASK,
        schedule_logic=ScheduleLogicType.EXACT_DATETIME_DEADLINE,
        title="Підготувати презентацію",
    )
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = created_dto

    await handle_deadline_priority_callback(cb2, cb_data2, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.reminder_type == ReminderType.DEADLINE_TASK
    assert cmd.schedule_logic == ScheduleLogicType.EXACT_DATETIME_DEADLINE
    assert cmd.base_priority is None
    assert cmd.lead_times == ["1d", "2h", "0d"]
    assert state.clear_called is True


@pytest.mark.asyncio
async def test_deadline_wizard_custom_date_and_explicit_priority() -> None:
    # 2. Введення користувацької дати дедлайну
    future_dt = datetime.now(ZoneInfo("Europe/Kyiv")) + timedelta(days=5)
    formatted_dt = future_dt.strftime("%d.%m.%Y %H:%M")

    msg, bot = _create_mock_message(formatted_dt)
    state = MockFSMContext(initial_data={"title": "Здати диплом"})
    current_user = _make_dummy_user(timezone="Europe/Kyiv")

    await handle_deadline_date_message(msg, state, current_user)

    assert "due_datetime_iso" in state.data
    assert state.current_state == DeadlineTaskCreateStates.waiting_for_priority

    # 3. Вибір пріоритету CRITICAL
    cb, bot2 = _create_mock_callback("wiz#dl_prio#CRITICAL")
    cb_data = CreateWizardCallback(step="dl_prio", value="CRITICAL")
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = _make_dummy_reminder(
        reminder_type=ReminderType.DEADLINE_TASK,
        schedule_logic=ScheduleLogicType.EXACT_DATETIME_DEADLINE,
        title="Здати диплом",
    )

    await handle_deadline_priority_callback(cb, cb_data, state, current_user, api_client)

    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.base_priority == Priority.CRITICAL


@pytest.mark.asyncio
async def test_deadline_past_date_rejected() -> None:
    # Дата в минулому
    msg, bot = _create_mock_message("01.01.2020 12:00")
    state = MockFSMContext(initial_data={"title": "Стара задача"})
    current_user = _make_dummy_user()

    await handle_deadline_date_message(msg, state, current_user)

    assert "повинні бути у майбутньому" in _get_sent_messages(bot)[0].text
    assert state.current_state is None


# =============================================================================
# Тести майстра SUBSCRIPTION
# =============================================================================


@pytest.mark.asyncio
async def test_subscription_regular_flow() -> None:
    # 1. Назва
    msg1, _ = _create_mock_message("Netflix Premium")
    state = MockFSMContext()
    await handle_subscription_title(msg1, state)
    assert state.data["title"] == "Netflix Premium"
    assert state.current_state == SubscriptionCreateStates.waiting_for_amount_currency

    # 2. Сума та валюта
    msg2, _ = _create_mock_message("9.99 USD")
    await handle_subscription_amount_currency(msg2, state)
    assert state.data["regular_amount"] == "9.99"
    assert state.data["currency"] == "USD"
    assert state.current_state == SubscriptionCreateStates.waiting_for_billing_day

    # 3. День списання через callback
    cb1, _ = _create_mock_callback("wiz#sub_bill#15_1")
    cb_data1 = CreateWizardCallback(step="sub_bill", value="15_1")
    current_user = _make_dummy_user()
    await handle_subscription_billing_callback(cb1, cb_data1, state, current_user)
    assert state.data["billing_day"] == 15
    assert state.data["interval_months"] == 1
    assert state.current_state == SubscriptionCreateStates.waiting_for_mode

    # 4. Режим "regular"
    cb2, _ = _create_mock_callback("wiz#sub_mode#regular")
    cb_data2 = CreateWizardCallback(step="sub_mode", value="regular")
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = _make_dummy_reminder(
        reminder_type=ReminderType.SUBSCRIPTION,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title="Netflix Premium",
        regular_amount=Decimal("9.99"),
        currency=CurrencyCode.USD,
    )

    await handle_subscription_mode_callback(cb2, cb_data2, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.reminder_type == ReminderType.SUBSCRIPTION
    assert cmd.regular_amount == Decimal("9.99")
    assert cmd.currency == CurrencyCode.USD
    assert cmd.is_trial is False
    assert cmd.lead_times == ["3d", "1d", "0d"]
    assert state.clear_called is True


@pytest.mark.asyncio
async def test_subscription_manual_billing_message() -> None:
    state = MockFSMContext(
        initial_data={
            "title": "Оренда квартири",
            "regular_amount": "15000",
            "currency": "UAH",
        }
    )
    # 1. Валідний день (25)
    msg1, _ = _create_mock_message("25")
    await handle_subscription_billing_message(msg1, state)
    assert state.data["billing_day"] == 25
    assert state.data["interval_months"] == 1
    assert state.current_state == SubscriptionCreateStates.waiting_for_mode

    # 2. Невалідний день (35)
    msg2, bot2 = _create_mock_message("35")
    await handle_subscription_billing_message(msg2, state)
    assert "Некоректний день місяця" in _get_sent_messages(bot2)[0].text


@pytest.mark.asyncio
async def test_subscription_trial_flow() -> None:
    state = MockFSMContext(
        initial_data={
            "title": "YouTube Premium",
            "regular_amount": "149.00",
            "currency": "UAH",
            "billing_day": 1,
            "interval_months": 1,
        }
    )
    current_user = _make_dummy_user()

    # Вибір режиму trial
    cb, bot = _create_mock_callback("wiz#sub_mode#trial")
    cb_data = CreateWizardCallback(step="sub_mode", value="trial")
    api_client = AsyncMock(spec=BackendApiClient)

    await handle_subscription_mode_callback(cb, cb_data, state, current_user, api_client)
    assert state.current_state == SubscriptionCreateStates.waiting_for_trial_date

    # Введення дати тріалу в майбутньому
    future_date = datetime.now(ZoneInfo("Europe/Kyiv")).date() + timedelta(days=30)
    msg, _ = _create_mock_message(future_date.strftime("%d.%m.%Y"))
    api_client.create_reminder.return_value = _make_dummy_reminder(
        reminder_type=ReminderType.SUBSCRIPTION,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title="YouTube Premium",
        is_trial=True,
        trial_end_date=future_date,
    )

    await handle_subscription_trial_date(msg, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.is_trial is True
    assert cmd.trial_end_date == future_date
    assert state.clear_called is True


@pytest.mark.asyncio
async def test_subscription_discount_flow() -> None:
    state = MockFSMContext(
        initial_data={
            "title": "Setapp",
            "regular_amount": "9.99",
            "currency": "USD",
            "billing_day": 5,
            "interval_months": 1,
        }
    )
    current_user = _make_dummy_user()

    # Вибір режиму discount
    cb, _ = _create_mock_callback("wiz#sub_mode#discount")
    cb_data = CreateWizardCallback(step="sub_mode", value="discount")
    api_client = AsyncMock(spec=BackendApiClient)
    await handle_subscription_mode_callback(cb, cb_data, state, current_user, api_client)
    assert state.current_state == SubscriptionCreateStates.waiting_for_discount_details

    # Введення акційної ціни та кількості циклів (2.99 на 3 цикли)
    msg, _ = _create_mock_message("2.99 3")
    api_client.create_reminder.return_value = _make_dummy_reminder(
        reminder_type=ReminderType.SUBSCRIPTION,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title="Setapp",
    )

    await handle_subscription_discount_details(msg, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.discount_amount == Decimal("2.99")
    assert cmd.discount_cycles_total == 3
    assert cmd.discount_cycles_remaining == 3
    assert state.clear_called is True


# =============================================================================
# Тести майстра MEDICATION
# =============================================================================


@pytest.mark.asyncio
async def test_medication_daily_flow() -> None:
    # 1. Назва та доза
    msg1, _ = _create_mock_message("Амоксиклав 1000 мг")
    state = MockFSMContext()
    await handle_medication_title(msg1, state)
    assert state.data["title"] == "Амоксиклав 1000 мг"
    assert state.current_state == MedicationCreateStates.waiting_for_schedule_mode

    # 2. Вибір щоденного режиму
    cb1, _ = _create_mock_callback("wiz#med_mode#daily")
    cb_data1 = CreateWizardCallback(step="med_mode", value="daily")
    await handle_medication_schedule_mode(cb1, cb_data1, state)
    assert state.data["med_mode"] == "daily"
    assert state.current_state == MedicationCreateStates.waiting_for_schedule_value

    # 3. Введення годин прийому
    msg2, _ = _create_mock_message("08:00, 14:00, 20:00")
    await handle_medication_schedule_value(msg2, state)
    assert state.data["schedule_logic"] == ScheduleLogicType.DAILY_AT_TIMES.value
    assert state.current_state == MedicationCreateStates.waiting_for_duration

    # 4. Вибір тривалості 7 днів через callback
    cb2, _ = _create_mock_callback("wiz#med_dur#7")
    cb_data2 = CreateWizardCallback(step="med_dur", value="7")
    current_user = _make_dummy_user()
    await handle_medication_duration_callback(cb2, cb_data2, state, current_user)
    assert state.data["course_duration_days"] == 7
    assert "start_date" in state.data
    assert "end_date" in state.data
    assert state.current_state == MedicationCreateStates.waiting_for_strict_mode

    # 5. Вибір нічного режиму (strict = True)
    cb3, _ = _create_mock_callback("wiz#med_strict#true")
    cb_data3 = CreateWizardCallback(step="med_strict", value="true")
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = _make_dummy_reminder(
        reminder_type=ReminderType.MEDICATION,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title="Амоксиклав 1000 мг",
        course_duration_days=7,
        strict_schedule=True,
    )

    await handle_medication_strict_callback(cb3, cb_data3, state, current_user, api_client)

    api_client.create_reminder.assert_awaited_once()
    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.reminder_type == ReminderType.MEDICATION
    assert cmd.schedule_logic == ScheduleLogicType.DAILY_AT_TIMES
    assert cmd.course_duration_days == 7
    assert cmd.strict_schedule is True
    assert state.clear_called is True


@pytest.mark.asyncio
async def test_medication_interval_flow_indefinite() -> None:
    state = MockFSMContext(
        initial_data={
            "title": "Вітамін D3",
            "med_mode": "interval",
        }
    )
    current_user = _make_dummy_user()

    # Інтервал кожні 12 годин
    msg1, _ = _create_mock_message("12")
    await handle_medication_schedule_value(msg1, state)
    assert state.data["schedule_logic"] == ScheduleLogicType.INTERVAL_HOURS.value

    # Тривалість 0 (безстроково) через повідомлення
    msg2, _ = _create_mock_message("0")
    await handle_medication_duration_message(msg2, state, current_user)
    assert state.data["course_duration_days"] is None
    assert state.data["start_date"] is None

    # М'який режим (strict = False)
    cb, _ = _create_mock_callback("wiz#med_strict#false")
    cb_data = CreateWizardCallback(step="med_strict", value="false")
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.create_reminder.return_value = _make_dummy_reminder(
        reminder_type=ReminderType.MEDICATION,
        schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
        title="Вітамін D3",
        strict_schedule=False,
    )

    await handle_medication_strict_callback(cb, cb_data, state, current_user, api_client)

    cmd: CreateReminderCommand = api_client.create_reminder.await_args[0][1]
    assert cmd.schedule_logic == ScheduleLogicType.INTERVAL_HOURS
    assert cmd.schedule_config["interval_hours"] == 12
    assert cmd.course_duration_days is None
    assert cmd.strict_schedule is False


# =============================================================================
# Тест реєстрації роутерів через setup_routers
# =============================================================================


def test_setup_routers_canonical_order() -> None:
    assert reminders_create_router.name == "reminders_create"
    dp = Dispatcher()
    setup_routers(dp)

    sub_router_names = [r.name for r in dp.sub_routers]
    expected_order = [
        "errors",
        "start",
        "reminders_create",
        "reminders_list",
        "reminders_actions",
        "finance",
        "settings",
    ]
    assert sub_router_names == expected_order
