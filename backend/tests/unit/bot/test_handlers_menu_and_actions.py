from datetime import UTC, datetime, time
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, ErrorEvent, Message, Update, User
from uuid6 import uuid7

from src.api.schemas.pagination import PaginatedResponse
from src.bot.callbacks.data import (
    ReminderActionCallback,
    ReminderDetailCallback,
    ReminderListFilterCallback,
    SettingsCallback,
)
from src.bot.client.api_client import BackendApiClient
from src.bot.client.exceptions import (
    BotApiConflictError,
    BotApiNotFoundError,
    BotApiValidationError,
)
from src.bot.handlers.errors import handle_bot_error
from src.bot.handlers.finance import handle_rates
from src.bot.handlers.reminders_actions import handle_reminder_action_callback
from src.bot.handlers.reminders_list import (
    handle_list_filter_callback,
    handle_list_reminders,
    handle_reminder_detail_callback,
)
from src.bot.handlers.settings import (
    handle_custom_quiet_hours_input,
    handle_custom_timezone_input,
    handle_settings,
    handle_settings_callback,
)
from src.bot.handlers.start import handle_cancel, handle_help, handle_start
from src.bot.keyboards import BTN_CANCEL, BTN_MY_REMINDERS, BTN_RATES, BTN_SETTINGS
from src.bot.states.settings_edit import SettingsEditStates
from src.modules.finance.domain.enums import ExchangeRateProvider as FinanceRateProvider
from src.modules.finance.queries.dto import ExchangeRateResponseDTO
from src.modules.reminders.application.dto import ReminderActionCommand, ReminderActionType
from src.modules.reminders.domain.enums import (
    MedicationLogStatus,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.queries.dto import (
    MedicationAdherenceStatsDTO,
    MedicationIntakeLogResponseDTO,
    ReminderResponseDTO,
)
from src.modules.users.application.dto import UpdateUserSettingsCommand
from src.modules.users.domain.enums import ExchangeRateProvider as UserRateProvider
from src.modules.users.domain.enums import UserRole
from src.modules.users.queries.dto import (
    TelegramAccountResponseDTO,
    UserResponseDTO,
    UserSettingsResponseDTO,
)


def _make_dummy_user(
    user_id: UUID | None = None,
    tg_id: int = 123456789,
    timezone: str = "Europe/Kyiv",
    preferred_bank: UserRateProvider = UserRateProvider.MONOBANK,
    escalate: bool = True,
    version: int = 1,
) -> UserResponseDTO:
    uid = user_id or uuid7()
    return UserResponseDTO(
        id=uid,
        username="tester",
        role=UserRole.USER,
        telegram_account=TelegramAccountResponseDTO(
            id=uuid7(),
            telegram_id=tg_id,
            telegram_chat_id=tg_id,
            tg_username="tester_tg",
            tg_full_name="Тестовий Користувач",
            version=1,
        ),
        settings=UserSettingsResponseDTO(
            id=uuid7(),
            user_id=uid,
            timezone=timezone,
            quiet_hours_start=time(23, 0),
            quiet_hours_end=time(8, 0),
            preferred_bank=preferred_bank,
            auto_deadline_priority_escalation=escalate,
            version=version,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_dummy_reminder(
    reminder_id: UUID | None = None,
    user_id: UUID | None = None,
    title: str = "Тестове завдання",
    reminder_type: ReminderType = ReminderType.OPEN_TASK,
    status: ReminderStatus = ReminderStatus.ACTIVE,
) -> ReminderResponseDTO:
    rid = reminder_id or uuid7()
    uid = user_id or uuid7()
    return ReminderResponseDTO(
        id=rid,
        user_id=uid,
        reminder_type=reminder_type,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title=title,
        description="Опис нагадування",
        status=status,
        next_trigger_at=datetime.now(UTC),
        schedule_config={"times": ["09:00", "18:00"]},
        lead_times=[],
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
    message_text: str = "Оригінальне сповіщення",
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
        id="cb_1",
        from_user=user,
        chat_instance="inst_1",
        data=data,
        message=msg,
    ).as_(bot_mock)
    return cb, bot_mock


def _get_sent_messages(bot: AsyncMock) -> list[SendMessage]:
    return [c[0][0] for c in bot.call_args_list if isinstance(c[0][0], SendMessage)]


def _get_edited_messages(bot: AsyncMock) -> list[EditMessageText]:
    return [c[0][0] for c in bot.call_args_list if isinstance(c[0][0], EditMessageText)]


def _get_callback_answers(bot: AsyncMock) -> list[AnswerCallbackQuery]:
    return [c[0][0] for c in bot.call_args_list if isinstance(c[0][0], AnswerCallbackQuery)]


# =============================================================================
# Тести Start & Help & Cancel
# =============================================================================


@pytest.mark.asyncio
async def test_handle_cancel() -> None:
    msg, bot = _create_mock_message(BTN_CANCEL)
    state = AsyncMock(spec=FSMContext)

    await handle_cancel(msg, state)

    state.clear.assert_awaited_once()
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "❌ Поточну дію скасовано." in sent[0].text
    assert sent[0].reply_markup is not None


@pytest.mark.asyncio
async def test_handle_start() -> None:
    msg, bot = _create_mock_message("/start")
    user = _make_dummy_user()
    state = AsyncMock(spec=FSMContext)

    await handle_start(msg, user, state)

    state.clear.assert_awaited_once()
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Вітаємо у Reminder App" in sent[0].text
    assert sent[0].reply_markup is not None


@pytest.mark.asyncio
async def test_handle_help() -> None:
    msg, bot = _create_mock_message("/help")

    await handle_help(msg)

    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Довідка щодо роботи з Reminder Bot" in sent[0].text
    assert sent[0].reply_markup is not None


# =============================================================================
# Тести Finance / Rates
# =============================================================================


@pytest.mark.asyncio
async def test_handle_rates() -> None:
    msg, bot = _create_mock_message(BTN_RATES)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    dummy_rates = [
        ExchangeRateResponseDTO(
            id=uuid7(),
            provider=FinanceRateProvider.MONOBANK,
            base_currency="UAH",
            target_currency="USD",
            rate_buy=Decimal("41.20"),
            rate_sell=Decimal("41.80"),
            created_at=datetime.now(UTC),
        ),
        ExchangeRateResponseDTO(
            id=uuid7(),
            provider=FinanceRateProvider.NBU,
            base_currency="UAH",
            target_currency="USD",
            rate_buy=None,
            rate_sell=Decimal("41.35"),
            created_at=datetime.now(UTC),
        ),
    ]
    api_client.get_latest_rates.return_value = dummy_rates

    await handle_rates(msg, user, api_client)

    api_client.get_latest_rates.assert_awaited_once_with(
        telegram_id=user.telegram_account.telegram_id  # type: ignore[union-attr]
    )
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Актуальні курси валют" in sent[0].text
    assert "41.20" in sent[0].text
    assert "Monobank" in sent[0].text


# =============================================================================
# Тести Settings
# =============================================================================


@pytest.mark.asyncio
async def test_handle_settings_message() -> None:
    msg, bot = _create_mock_message(BTN_SETTINGS)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings

    await handle_settings(msg, user, api_client)

    api_client.get_user_settings.assert_awaited_once_with(
        user.telegram_account.telegram_id  # type: ignore[union-attr]
    )
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Ваші налаштування" in sent[0].text


@pytest.mark.asyncio
async def test_handle_settings_callback_menu() -> None:
    cb, bot = _create_mock_callback("cfg#menu#main")
    cb_data = SettingsCallback(section="menu", value="main")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings
    state = AsyncMock(spec=FSMContext)

    await handle_settings_callback(cb, cb_data, user, api_client, state)

    state.clear.assert_awaited_once()
    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    assert edited[0].text is not None
    assert "Ваші налаштування" in edited[0].text
    answers = _get_callback_answers(bot)
    assert len(answers) == 1


@pytest.mark.asyncio
async def test_handle_settings_callback_bank_menu() -> None:
    cb, bot = _create_mock_callback("cfg#bank#menu")
    cb_data = SettingsCallback(section="bank", value="menu")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings
    state = AsyncMock(spec=FSMContext)

    await handle_settings_callback(cb, cb_data, user, api_client, state)

    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    assert edited[0].text is not None
    assert "Оберіть пріоритетний банк" in edited[0].text
    answers = _get_callback_answers(bot)
    assert len(answers) == 1


@pytest.mark.asyncio
async def test_handle_settings_callback_bank_update() -> None:
    cb, bot = _create_mock_callback("cfg#bank#PRIVATBANK")
    cb_data = SettingsCallback(section="bank", value="PRIVATBANK")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings

    updated_settings = user.settings.model_copy(update={"preferred_bank": UserRateProvider.PRIVATBANK, "version": 2})
    api_client.update_user_settings.return_value = updated_settings
    state = AsyncMock(spec=FSMContext)

    await handle_settings_callback(cb, cb_data, user, api_client, state)

    api_client.update_user_settings.assert_awaited_once()
    cmd = api_client.update_user_settings.call_args[0][1]
    assert isinstance(cmd, UpdateUserSettingsCommand)
    assert cmd.preferred_bank == UserRateProvider.PRIVATBANK
    assert cmd.version == 1

    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "✅ Пріоритетний банк оновлено!"


@pytest.mark.asyncio
async def test_handle_settings_callback_escalate_toggle() -> None:
    cb, bot = _create_mock_callback("cfg#escalate#toggle")
    cb_data = SettingsCallback(section="escalate", value="toggle")
    user = _make_dummy_user(escalate=True)
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings

    updated_settings = user.settings.model_copy(update={"auto_deadline_priority_escalation": False, "version": 2})
    api_client.update_user_settings.return_value = updated_settings
    state = AsyncMock(spec=FSMContext)

    await handle_settings_callback(cb, cb_data, user, api_client, state)

    cmd = api_client.update_user_settings.call_args[0][1]
    assert cmd.auto_deadline_priority_escalation is False
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "✅ Налаштування автоескалації змінено!"


@pytest.mark.asyncio
async def test_handle_settings_callback_quiet_preset() -> None:
    cb, bot = _create_mock_callback("cfg#quiet#22:00-07:00")
    cb_data = SettingsCallback(section="quiet", value="22:00-07:00")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings
    api_client.update_user_settings.return_value = user.settings
    state = AsyncMock(spec=FSMContext)

    await handle_settings_callback(cb, cb_data, user, api_client, state)

    cmd = api_client.update_user_settings.call_args[0][1]
    assert cmd.quiet_hours_start == time(22, 0)
    assert cmd.quiet_hours_end == time(7, 0)
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "✅ Тихі години оновлено!"


@pytest.mark.asyncio
async def test_handle_settings_callback_quiet_custom_prompt() -> None:
    cb, bot = _create_mock_callback("cfg#quiet#custom")
    cb_data = SettingsCallback(section="quiet", value="custom")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    state = AsyncMock(spec=FSMContext)

    await handle_settings_callback(cb, cb_data, user, api_client, state)

    state.set_state.assert_awaited_once_with(SettingsEditStates.waiting_for_custom_quiet_hours)
    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    assert edited[0].text is not None
    assert "Введіть інтервал тихих годин" in edited[0].text


@pytest.mark.asyncio
async def test_handle_settings_callback_tz_preset() -> None:
    cb, bot = _create_mock_callback("cfg#tz#Europe/Warsaw")
    cb_data = SettingsCallback(section="tz", value="Europe/Warsaw")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings
    api_client.update_user_settings.return_value = user.settings
    state = AsyncMock(spec=FSMContext)

    await handle_settings_callback(cb, cb_data, user, api_client, state)

    cmd = api_client.update_user_settings.call_args[0][1]
    assert cmd.timezone == "Europe/Warsaw"
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "✅ Часовий пояс оновлено!"


@pytest.mark.asyncio
async def test_handle_custom_quiet_hours_input_invalid() -> None:
    msg, bot = _create_mock_message("invalid_time")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    state = AsyncMock(spec=FSMContext)

    await handle_custom_quiet_hours_input(msg, user, api_client, state)

    state.clear.assert_not_called()
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Некоректний формат часу" in sent[0].text


@pytest.mark.asyncio
async def test_handle_custom_quiet_hours_input_valid() -> None:
    msg, bot = _create_mock_message("01:30-09:15")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings
    api_client.update_user_settings.return_value = user.settings
    state = AsyncMock(spec=FSMContext)

    await handle_custom_quiet_hours_input(msg, user, api_client, state)

    state.clear.assert_awaited_once()
    cmd = api_client.update_user_settings.call_args[0][1]
    assert cmd.quiet_hours_start == time(1, 30)
    assert cmd.quiet_hours_end == time(9, 15)
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Тихі години успішно встановлено" in sent[0].text


@pytest.mark.asyncio
async def test_handle_custom_timezone_input_invalid() -> None:
    msg, bot = _create_mock_message("Moon/Base")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    state = AsyncMock(spec=FSMContext)

    await handle_custom_timezone_input(msg, user, api_client, state)

    state.clear.assert_not_called()
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Невідомий або некоректний часовий пояс" in sent[0].text


@pytest.mark.asyncio
async def test_handle_custom_timezone_input_valid() -> None:
    msg, bot = _create_mock_message("America/New_York")
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    api_client.get_user_settings.return_value = user.settings
    api_client.update_user_settings.return_value = user.settings
    state = AsyncMock(spec=FSMContext)

    await handle_custom_timezone_input(msg, user, api_client, state)

    state.clear.assert_awaited_once()
    cmd = api_client.update_user_settings.call_args[0][1]
    assert cmd.timezone == "America/New_York"
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Часовий пояс успішно оновлено" in sent[0].text


# =============================================================================
# Тести Reminders List & Detail
# =============================================================================


@pytest.mark.asyncio
async def test_handle_list_reminders() -> None:
    msg, bot = _create_mock_message(BTN_MY_REMINDERS)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(user_id=user.id)
    page_data = PaginatedResponse[ReminderResponseDTO](
        items=[rem],
        total=1,
        page=1,
        size=5,
        pages=1,
    )
    api_client.list_reminders.return_value = page_data

    await handle_list_reminders(msg, user, api_client)

    api_client.list_reminders.assert_awaited_once_with(
        user.telegram_account.telegram_id,  # type: ignore[union-attr]
        page=1,
        size=5,
    )
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert "Ваші нагадування (Усі категорії)" in sent[0].text
    assert rem.title in sent[0].text


@pytest.mark.asyncio
async def test_handle_list_filter_callback() -> None:
    cb, bot = _create_mock_callback("rem_list:MEDICATION:2")
    cb_data = ReminderListFilterCallback(category="MEDICATION", page=2)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    page_data = PaginatedResponse[ReminderResponseDTO](
        items=[],
        total=0,
        page=2,
        size=5,
        pages=1,
    )
    api_client.list_reminders.return_value = page_data

    await handle_list_filter_callback(cb, cb_data, user, api_client)

    api_client.list_reminders.assert_awaited_once_with(
        user.telegram_account.telegram_id,  # type: ignore[union-attr]
        page=2,
        size=5,
        reminder_type=ReminderType.MEDICATION,
    )
    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    answers = _get_callback_answers(bot)
    assert len(answers) == 1


@pytest.mark.asyncio
async def test_handle_reminder_detail_callback_view() -> None:
    rem_id = uuid7()
    cb, bot = _create_mock_callback(f"rem_det:view:{rem_id}")
    cb_data = ReminderDetailCallback(action="view", reminder_id=rem_id)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(reminder_id=rem_id, user_id=user.id)
    api_client.get_reminder.return_value = rem

    await handle_reminder_detail_callback(cb, cb_data, user, api_client)

    api_client.get_reminder.assert_awaited_once_with(
        user.telegram_account.telegram_id,  # type: ignore[union-attr]
        rem_id,
    )
    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    assert edited[0].text is not None
    assert rem.title in edited[0].text
    answers = _get_callback_answers(bot)
    assert len(answers) == 1


@pytest.mark.asyncio
async def test_handle_reminder_detail_callback_done() -> None:
    rem_id = uuid7()
    cb, bot = _create_mock_callback(f"rem_det:done:{rem_id}")
    cb_data = ReminderDetailCallback(action="done", reminder_id=rem_id)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(reminder_id=rem_id, user_id=user.id, status=ReminderStatus.COMPLETED)
    api_client.perform_reminder_action.return_value = rem

    await handle_reminder_detail_callback(cb, cb_data, user, api_client)

    cmd = api_client.perform_reminder_action.call_args[0][2]
    assert isinstance(cmd, ReminderActionCommand)
    assert cmd.action == ReminderActionType.COMPLETE
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "✅ Позначено як виконане!"


@pytest.mark.asyncio
async def test_handle_reminder_detail_callback_pause_resume() -> None:
    rem_id = uuid7()
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(reminder_id=rem_id, user_id=user.id)
    api_client.perform_reminder_action.return_value = rem

    # Pause
    cb_pause, bot_pause = _create_mock_callback(f"rem_det:pause:{rem_id}")
    await handle_reminder_detail_callback(
        cb_pause,
        ReminderDetailCallback(action="pause", reminder_id=rem_id),
        user,
        api_client,
    )
    assert api_client.perform_reminder_action.call_args[0][2].action == ReminderActionType.PAUSE
    answers_pause = _get_callback_answers(bot_pause)
    assert len(answers_pause) == 1
    assert answers_pause[0].text == "⏸ Нагадування призупинено"

    # Resume
    cb_resume, bot_resume = _create_mock_callback(f"rem_det:resume:{rem_id}")
    await handle_reminder_detail_callback(
        cb_resume,
        ReminderDetailCallback(action="resume", reminder_id=rem_id),
        user,
        api_client,
    )
    assert api_client.perform_reminder_action.call_args[0][2].action == ReminderActionType.RESUME
    answers_resume = _get_callback_answers(bot_resume)
    assert len(answers_resume) == 1
    assert answers_resume[0].text == "▶️ Нагадування відновлено"


@pytest.mark.asyncio
async def test_handle_reminder_detail_callback_stats() -> None:
    rem_id = uuid7()
    cb, bot = _create_mock_callback(f"rem_det:stats:{rem_id}")
    cb_data = ReminderDetailCallback(action="stats", reminder_id=rem_id)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(reminder_id=rem_id, user_id=user.id, reminder_type=ReminderType.MEDICATION)
    stats = MedicationAdherenceStatsDTO(
        reminder_id=rem_id,
        total_logs=10,
        taken_count=9,
        snoozed_count=1,
        missed_count=0,
        adherence_rate_percent=90.0,
        logs=[
            MedicationIntakeLogResponseDTO(
                id=uuid7(),
                reminder_id=rem_id,
                scheduled_at=datetime.now(UTC),
                recorded_at=datetime.now(UTC),
                status=MedicationLogStatus.TAKEN,
                created_at=datetime.now(UTC),
                version=1,
            )
        ],
    )
    api_client.get_reminder.return_value = rem
    api_client.get_medication_logs.return_value = stats

    await handle_reminder_detail_callback(cb, cb_data, user, api_client)

    api_client.get_medication_logs.assert_awaited_once_with(
        user.telegram_account.telegram_id,  # type: ignore[union-attr]
        rem_id,
    )
    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    assert edited[0].text is not None
    assert "90.0%" in edited[0].text
    assert "Статистика прийому ліків" in edited[0].text
    answers = _get_callback_answers(bot)
    assert len(answers) == 1


@pytest.mark.asyncio
async def test_handle_reminder_detail_callback_delete() -> None:
    rem_id = uuid7()
    cb, bot = _create_mock_callback(f"rem_det:delete:{rem_id}")
    cb_data = ReminderDetailCallback(action="delete", reminder_id=rem_id)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    page_data = PaginatedResponse[ReminderResponseDTO](
        items=[],
        total=0,
        page=1,
        size=5,
        pages=1,
    )
    api_client.list_reminders.return_value = page_data

    await handle_reminder_detail_callback(cb, cb_data, user, api_client)

    api_client.delete_reminder.assert_awaited_once_with(
        user.telegram_account.telegram_id,  # type: ignore[union-attr]
        rem_id,
        hard=False,
    )
    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "🗑 Нагадування видалено"


# =============================================================================
# Тести Reminder Notification Action Handlers
# =============================================================================


@pytest.mark.asyncio
async def test_handle_reminder_action_payment() -> None:
    rem_id = uuid7()
    cb, bot = _create_mock_callback(f"reminder:payment:{rem_id}:0", message_text="Оплатіть підписку Netflix")
    cb_data = ReminderActionCallback(action="payment", reminder_id=rem_id, minutes=0)
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(reminder_id=rem_id, user_id=user.id, reminder_type=ReminderType.SUBSCRIPTION)
    api_client.perform_reminder_action.return_value = rem

    await handle_reminder_action_callback(cb, cb_data, user, api_client)

    api_client.perform_reminder_action.assert_awaited_once()
    cmd = api_client.perform_reminder_action.call_args[0][2]
    assert cmd.action == ReminderActionType.RECORD_PAYMENT

    edited = _get_edited_messages(bot)
    assert len(edited) == 1
    assert edited[0].reply_markup is None  # Інлайн-кнопки прибрано!
    assert edited[0].text is not None
    assert "Оплату підписки зафіксовано" in edited[0].text
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "✅ Дію виконано!"


@pytest.mark.asyncio
async def test_handle_reminder_action_med_taken_and_missed() -> None:
    rem_id = uuid7()
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(reminder_id=rem_id, user_id=user.id, reminder_type=ReminderType.MEDICATION)
    api_client.perform_reminder_action.return_value = rem

    # Taken
    cb_taken, bot_taken = _create_mock_callback(f"reminder:med_taken:{rem_id}:0")
    await handle_reminder_action_callback(
        cb_taken,
        ReminderActionCallback(action="med_taken", reminder_id=rem_id, minutes=0),
        user,
        api_client,
    )
    cmd_taken = api_client.perform_reminder_action.call_args[0][2]
    assert cmd_taken.action == ReminderActionType.RECORD_MEDICATION_INTAKE
    assert cmd_taken.medication_status == MedicationLogStatus.TAKEN
    edited_taken = _get_edited_messages(bot_taken)
    assert len(edited_taken) == 1
    assert edited_taken[0].text is not None
    assert "Прийом ліків зафіксовано" in edited_taken[0].text

    # Missed
    cb_missed, bot_missed = _create_mock_callback(f"reminder:med_missed:{rem_id}:0")
    await handle_reminder_action_callback(
        cb_missed,
        ReminderActionCallback(action="med_missed", reminder_id=rem_id, minutes=0),
        user,
        api_client,
    )
    cmd_missed = api_client.perform_reminder_action.call_args[0][2]
    assert cmd_missed.action == ReminderActionType.RECORD_MEDICATION_INTAKE
    assert cmd_missed.medication_status == MedicationLogStatus.MISSED
    edited_missed = _get_edited_messages(bot_missed)
    assert len(edited_missed) == 1
    assert edited_missed[0].text is not None
    assert "Прийом ліків позначено як пропущений" in edited_missed[0].text


@pytest.mark.asyncio
async def test_handle_reminder_action_complete_cancel_snooze() -> None:
    rem_id = uuid7()
    user = _make_dummy_user()
    api_client = AsyncMock(spec=BackendApiClient)
    rem = _make_dummy_reminder(reminder_id=rem_id, user_id=user.id)
    api_client.perform_reminder_action.return_value = rem

    # Complete
    cb_complete, bot_complete = _create_mock_callback(f"reminder:complete:{rem_id}:0")
    await handle_reminder_action_callback(
        cb_complete,
        ReminderActionCallback(action="complete", reminder_id=rem_id, minutes=0),
        user,
        api_client,
    )
    assert api_client.perform_reminder_action.call_args[0][2].action == ReminderActionType.COMPLETE
    edited_complete = _get_edited_messages(bot_complete)
    assert len(edited_complete) == 1
    assert edited_complete[0].text is not None
    assert "Нагадування позначено як виконане" in edited_complete[0].text

    # Cancel
    cb_cancel, bot_cancel = _create_mock_callback(f"reminder:cancel:{rem_id}:0")
    await handle_reminder_action_callback(
        cb_cancel,
        ReminderActionCallback(action="cancel", reminder_id=rem_id, minutes=0),
        user,
        api_client,
    )
    assert api_client.perform_reminder_action.call_args[0][2].action == ReminderActionType.CANCEL
    edited_cancel = _get_edited_messages(bot_cancel)
    assert len(edited_cancel) == 1
    assert edited_cancel[0].text is not None
    assert "Підписку успішно скасовано" in edited_cancel[0].text

    # Snooze
    cb_snooze, bot_snooze = _create_mock_callback(f"reminder:snooze:{rem_id}:60")
    await handle_reminder_action_callback(
        cb_snooze,
        ReminderActionCallback(action="snooze", reminder_id=rem_id, minutes=60),
        user,
        api_client,
    )
    cmd_snooze = api_client.perform_reminder_action.call_args[0][2]
    assert cmd_snooze.action == ReminderActionType.SNOOZE
    assert cmd_snooze.snooze_minutes == 60
    edited_snooze = _get_edited_messages(bot_snooze)
    assert len(edited_snooze) == 1
    assert edited_snooze[0].text is not None
    assert "Відкладено на 60 хв" in edited_snooze[0].text


# =============================================================================
# Тести Global Error Handler
# =============================================================================


@pytest.mark.asyncio
async def test_handle_bot_error_conflict_on_callback() -> None:
    cb, bot = _create_mock_callback("cfg#bank#NBU")
    update = Update(update_id=101, callback_query=cb)
    event = ErrorEvent(
        update=update,
        exception=BotApiConflictError(message="OCC Conflict"),
    )

    handled = await handle_bot_error(event)

    assert handled is True
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "⚠️ Дані були змінені паралельно. Оновіть меню та спробуйте ще раз."
    assert answers[0].show_alert is True


@pytest.mark.asyncio
async def test_handle_bot_error_not_found_on_message() -> None:
    msg, bot = _create_mock_message("/list")
    update = Update(update_id=102, message=msg)
    event = ErrorEvent(
        update=update,
        exception=BotApiNotFoundError(message="Reminder not found"),
    )

    handled = await handle_bot_error(event)

    assert handled is True
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert sent[0].text == "⚠️ Запис не знайдено або вже видалено."


@pytest.mark.asyncio
async def test_handle_bot_error_validation_on_message() -> None:
    msg, bot = _create_mock_message("/start")
    update = Update(update_id=103, message=msg)
    event = ErrorEvent(
        update=update,
        exception=BotApiValidationError(message="Invalid format of data"),
    )

    handled = await handle_bot_error(event)

    assert handled is True
    sent = _get_sent_messages(bot)
    assert len(sent) == 1
    assert sent[0].text == "⚠️ Некоректні дані: Invalid format of data"


@pytest.mark.asyncio
async def test_handle_bot_error_generic_exception() -> None:
    cb, bot = _create_mock_callback("some:data")
    update = Update(update_id=104, callback_query=cb)
    event = ErrorEvent(
        update=update,
        exception=RuntimeError("Unexpected connection drop"),
    )

    handled = await handle_bot_error(event)

    assert handled is True
    answers = _get_callback_answers(bot)
    assert len(answers) == 1
    assert answers[0].text == "⚠️ Тимчасова помилка зв'язку із сервером. Спробуйте за кілька секунд."
    assert answers[0].show_alert is True
