import asyncio
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    User,
)
from uuid6 import uuid7

from src.api.schemas.pagination import PaginatedResponse
from src.bot.callbacks import (
    CreateReminderTypeCallback,
    CreateWizardCallback,
    ReminderActionCallback,
    ReminderDetailCallback,
    ReminderListFilterCallback,
    SettingsCallback,
)
from src.bot.client.api_client import BackendApiClient
from src.bot.consumer import RedisNotificationConsumer
from src.bot.keyboards import (
    BTN_CANCEL,
    BTN_CREATE_REMINDER,
    BTN_MY_REMINDERS,
    BTN_RATES,
    BTN_SETTINGS,
    build_anniversary_lead_times_keyboard,
    build_bank_selection_keyboard,
    build_cancel_reply_keyboard,
    build_create_reminder_type_keyboard,
    build_deadline_priority_keyboard,
    build_deadline_quick_date_keyboard,
    build_main_reply_keyboard,
    build_medication_duration_keyboard,
    build_medication_schedule_mode_keyboard,
    build_medication_strict_keyboard,
    build_notification_keyboard,
    build_open_task_times_keyboard,
    build_quiet_hours_keyboard,
    build_reminder_detail_keyboard,
    build_reminders_list_keyboard,
    build_settings_main_keyboard,
    build_subscription_billing_keyboard,
    build_subscription_mode_keyboard,
    build_timezone_selection_keyboard,
)
from src.bot.middlewares import BotAuthMiddleware, BotLoggingMiddleware
from src.core.domain.enums import SystemRole
from src.infrastructure.notifications.dto import (
    DigestTaskItemDTO,
    NotificationEventType,
    NotificationPayload,
)
from src.modules.finance.public import ExchangeRateProvider
from src.modules.reminders.domain.enums import ReminderStatus, ReminderType, ScheduleLogicType
from src.modules.reminders.queries.dto import ReminderResponseDTO
from src.modules.users.queries.dto import (
    TelegramAccountResponseDTO,
    UserResponseDTO,
    UserSettingsResponseDTO,
)


def _make_dummy_user_dto(user_id: UUID, tg_id: int = 123456789) -> UserResponseDTO:
    return UserResponseDTO(
        id=user_id,
        username="test_user",
        role=SystemRole.USER,
        telegram_account=TelegramAccountResponseDTO(
            id=uuid7(),
            telegram_id=tg_id,
            telegram_chat_id=tg_id,
            tg_username="tg_tester",
            tg_full_name="Тестовий Користувач",
            version=1,
        ),
        settings=UserSettingsResponseDTO(
            id=uuid7(),
            user_id=user_id,
            timezone="Europe/Kyiv",
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


def _make_dummy_reminder_dto(
    reminder_id: UUID,
    user_id: UUID,
    title: str = "Тестове нагадування",
    reminder_type: ReminderType = ReminderType.OPEN_TASK,
    status: ReminderStatus = ReminderStatus.ACTIVE,
) -> ReminderResponseDTO:
    return ReminderResponseDTO(
        id=reminder_id,
        user_id=user_id,
        reminder_type=reminder_type,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title=title,
        description="Опис нагадування",
        status=status,
        schedule_config={"times": ["09:00", "18:00"]},
        lead_times=[],
        next_trigger_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        version=1,
    )


# =============================================================================
# Тести Reply-клавіатур
# =============================================================================


def test_build_main_reply_keyboard() -> None:
    kb = build_main_reply_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup)
    assert kb.resize_keyboard is True
    assert kb.is_persistent is True
    assert len(kb.keyboard) == 2
    assert [btn.text for btn in kb.keyboard[0]] == [BTN_CREATE_REMINDER, BTN_MY_REMINDERS]
    assert [btn.text for btn in kb.keyboard[1]] == [BTN_RATES, BTN_SETTINGS]


def test_build_cancel_reply_keyboard() -> None:
    kb = build_cancel_reply_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup)
    assert kb.resize_keyboard is True
    assert kb.is_persistent is True
    assert len(kb.keyboard) == 1
    assert kb.keyboard[0][0].text == BTN_CANCEL


# =============================================================================
# Тести Inline-клавіатур нагадувань
# =============================================================================


def test_build_notification_keyboard() -> None:
    # 1. Порожнє або None нагадування
    assert build_notification_keyboard(NotificationPayload(recipient_chat_id=123)) is None

    # 2. Щоденний дайджест: порожній -> None
    assert (
        build_notification_keyboard(
            NotificationPayload(
                event_type=NotificationEventType.DAILY_DIGEST,
                recipient_chat_id=123,
                digest_tasks=[],
            )
        )
        is None
    )

    # 3. Щоденний дайджест зі справами
    digest_kb = build_notification_keyboard(
        NotificationPayload(
            event_type=NotificationEventType.DAILY_DIGEST,
            recipient_chat_id=123,
            digest_tasks=[
                DigestTaskItemDTO(reminder_id=uuid7(), title="Справа 1"),
            ],
        )
    )
    assert isinstance(digest_kb, InlineKeyboardMarkup)
    assert len(digest_kb.inline_keyboard) == 1
    assert digest_kb.inline_keyboard[0][0].text == "📋 Відкрити мої справи"
    cb_filter = ReminderListFilterCallback.unpack(digest_kb.inline_keyboard[0][0].callback_data or "")
    assert cb_filter.category == ReminderType.OPEN_TASK.value
    assert cb_filter.page == 1

    # 4. Завершення тріалу
    rem_id = uuid7()
    trial_kb = build_notification_keyboard(
        NotificationPayload(
            event_type=NotificationEventType.TRIAL_EXPIRED,
            recipient_chat_id=123,
            reminder_id=rem_id,
            reminder_type=ReminderType.SUBSCRIPTION,
        )
    )
    assert isinstance(trial_kb, InlineKeyboardMarkup)
    assert len(trial_kb.inline_keyboard) == 1
    assert len(trial_kb.inline_keyboard[0]) == 2
    assert trial_kb.inline_keyboard[0][0].text == "💳 Оплачено"
    assert trial_kb.inline_keyboard[0][1].text == "❌ Скасувати підписку"
    cb_pay = ReminderActionCallback.unpack(trial_kb.inline_keyboard[0][0].callback_data or "")
    assert cb_pay.action == "payment"
    assert cb_pay.reminder_id == rem_id

    # 5. Підписка (SUBSCRIPTION)
    sub_kb = build_notification_keyboard(
        NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=rem_id,
            reminder_type=ReminderType.SUBSCRIPTION,
        )
    )
    assert isinstance(sub_kb, InlineKeyboardMarkup)
    assert len(sub_kb.inline_keyboard) == 2
    assert len(sub_kb.inline_keyboard[0]) == 2
    assert len(sub_kb.inline_keyboard[1]) == 1
    assert sub_kb.inline_keyboard[0][0].text == "💳 Оплачено"
    assert sub_kb.inline_keyboard[0][1].text == "⏰ Нагадати завтра"
    assert sub_kb.inline_keyboard[1][0].text == "❌ Скасувати підписку"
    cb_snooze_sub = ReminderActionCallback.unpack(sub_kb.inline_keyboard[0][1].callback_data or "")
    assert cb_snooze_sub.minutes == 1440

    # 6. Ліки (MEDICATION)
    med_kb = build_notification_keyboard(
        NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=rem_id,
            reminder_type=ReminderType.MEDICATION,
        )
    )
    assert isinstance(med_kb, InlineKeyboardMarkup)
    assert len(med_kb.inline_keyboard) == 2
    assert len(med_kb.inline_keyboard[0]) == 2
    assert len(med_kb.inline_keyboard[1]) == 1
    assert med_kb.inline_keyboard[0][0].text == "💊 Прийняв"
    assert med_kb.inline_keyboard[0][1].text == "⏰ +15 хв"
    assert med_kb.inline_keyboard[1][0].text == "❌ Пропустив"
    cb_snooze_med = ReminderActionCallback.unpack(med_kb.inline_keyboard[0][1].callback_data or "")
    assert cb_snooze_med.minutes == 15

    # 7. Дедлайн (DEADLINE_TASK)
    dl_kb = build_notification_keyboard(
        NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=rem_id,
            reminder_type=ReminderType.DEADLINE_TASK,
        )
    )
    assert isinstance(dl_kb, InlineKeyboardMarkup)
    assert len(dl_kb.inline_keyboard) == 1
    assert len(dl_kb.inline_keyboard[0]) == 2
    assert dl_kb.inline_keyboard[0][0].text == "✅ Виконано"
    assert dl_kb.inline_keyboard[0][1].text == "⏰ +1 год"
    cb_snooze_dl = ReminderActionCallback.unpack(dl_kb.inline_keyboard[0][1].callback_data or "")
    assert cb_snooze_dl.minutes == 60

    # 8. Річниця (ANNIVERSARY)
    anniv_kb = build_notification_keyboard(
        NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=rem_id,
            reminder_type=ReminderType.ANNIVERSARY,
        )
    )
    assert isinstance(anniv_kb, InlineKeyboardMarkup)
    assert len(anniv_kb.inline_keyboard) == 1
    assert len(anniv_kb.inline_keyboard[0]) == 1
    assert anniv_kb.inline_keyboard[0][0].text == "✅ Привітав"

    # 9. Відкрита справа (OPEN_TASK)
    open_kb = build_notification_keyboard(
        NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=rem_id,
            reminder_type=ReminderType.OPEN_TASK,
        )
    )
    assert isinstance(open_kb, InlineKeyboardMarkup)
    assert len(open_kb.inline_keyboard) == 1
    assert len(open_kb.inline_keyboard[0]) == 2
    assert open_kb.inline_keyboard[0][0].text == "✅ Виконано"
    assert open_kb.inline_keyboard[0][1].text == "⏰ Відкласти"
    cb_snooze_open = ReminderActionCallback.unpack(open_kb.inline_keyboard[0][1].callback_data or "")
    assert cb_snooze_open.minutes == 180


def test_build_create_reminder_type_keyboard() -> None:
    kb = build_create_reminder_type_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 5

    types_in_kb = []
    for row in kb.inline_keyboard:
        cb = CreateReminderTypeCallback.unpack(row[0].callback_data or "")
        types_in_kb.append(cb.reminder_type)

    assert types_in_kb == [
        ReminderType.OPEN_TASK.value,
        ReminderType.ANNIVERSARY.value,
        ReminderType.DEADLINE_TASK.value,
        ReminderType.SUBSCRIPTION.value,
        ReminderType.MEDICATION.value,
    ]


def test_build_reminders_list_keyboard_categories_and_items() -> None:
    user_id = uuid7()
    rem1 = _make_dummy_reminder_dto(uuid7(), user_id, title="Купити молоко", reminder_type=ReminderType.OPEN_TASK)
    rem2 = _make_dummy_reminder_dto(
        uuid7(),
        user_id,
        title="Дуже довга назва справи, яка перевищує тридцять два символи",
        reminder_type=ReminderType.ANNIVERSARY,
    )

    page_data = PaginatedResponse[ReminderResponseDTO](
        items=[rem1, rem2],
        total=2,
        page=1,
        size=5,
        pages=1,
    )

    kb = build_reminders_list_keyboard(page_data, category="ANNIVERSARY")
    assert isinstance(kb, InlineKeyboardMarkup)

    # Рядок фільтрів
    filter_row = kb.inline_keyboard[0]
    assert len(filter_row) == 6
    # Активна категорія ANNIVERSARY виділена крапками
    assert filter_row[0].text == "Усі"
    assert filter_row[1].text == "• 🎂 •"
    assert filter_row[2].text == "📝"

    # Рядки списку
    assert kb.inline_keyboard[1][0].text == "Купити молоко"
    # Перевірка обрізання до 32 символів
    assert kb.inline_keyboard[2][0].text == rem2.title[:32]
    assert len(kb.inline_keyboard[2][0].text) == 32

    # Оскільки pages == 1, рядок пагінації відсутній
    assert len(kb.inline_keyboard) == 3


def test_build_reminders_list_keyboard_pagination() -> None:
    user_id = uuid7()
    rem1 = _make_dummy_reminder_dto(uuid7(), user_id, title="Справа 1")
    page_data_p1 = PaginatedResponse[ReminderResponseDTO](items=[rem1], total=10, page=1, size=5, pages=2)

    kb_p1 = build_reminders_list_keyboard(page_data_p1, category="ALL")
    # Має бути тільки кнопка "Наступна ➡️"
    pagination_row_p1 = kb_p1.inline_keyboard[-1]
    assert len(pagination_row_p1) == 1
    assert "Наступна ➡️" in pagination_row_p1[0].text
    cb_next = ReminderListFilterCallback.unpack(pagination_row_p1[0].callback_data or "")
    assert cb_next.page == 2

    page_data_p2 = PaginatedResponse[ReminderResponseDTO](items=[rem1], total=10, page=2, size=5, pages=2)
    kb_p2 = build_reminders_list_keyboard(page_data_p2, category="ALL")
    # Має бути тільки кнопка "⬅️ Попередня"
    pagination_row_p2 = kb_p2.inline_keyboard[-1]
    assert len(pagination_row_p2) == 1
    assert "⬅️ Попередня" in pagination_row_p2[0].text
    cb_prev = ReminderListFilterCallback.unpack(pagination_row_p2[0].callback_data or "")
    assert cb_prev.page == 1

    # Сторінка 2 з 3 — обидві кнопки
    page_data_p2_of_3 = PaginatedResponse[ReminderResponseDTO](items=[rem1], total=15, page=2, size=5, pages=3)
    kb_p2_of_3 = build_reminders_list_keyboard(page_data_p2_of_3, category="ALL")
    pagination_row_mid = kb_p2_of_3.inline_keyboard[-1]
    assert len(pagination_row_mid) == 2
    assert "⬅️ Попередня" in pagination_row_mid[0].text
    assert "Наступна ➡️" in pagination_row_mid[1].text


def test_build_reminder_detail_keyboard() -> None:
    user_id = uuid7()
    rem_active = _make_dummy_reminder_dto(
        uuid7(), user_id, reminder_type=ReminderType.MEDICATION, status=ReminderStatus.ACTIVE
    )
    kb_active = build_reminder_detail_keyboard(rem_active)

    # Рядок 0: Done, Pause
    assert kb_active.inline_keyboard[0][0].text == "✅ Виконано"
    cb_done = ReminderDetailCallback.unpack(kb_active.inline_keyboard[0][0].callback_data or "")
    assert cb_done.action == "done"
    assert cb_done.reminder_id == rem_active.id
    assert kb_active.inline_keyboard[0][1].text == "⏸ Пауза"
    # Рядок 1: Статистика для ліків
    assert kb_active.inline_keyboard[1][0].text == "📊 Статистика прийому"
    # Рядок 2: Видалити
    assert kb_active.inline_keyboard[2][0].text == "🗑 Видалити"
    # Рядок 3: Назад
    assert kb_active.inline_keyboard[3][0].text == "⬅️ Назад до списку"

    # Пауза -> Відновити
    rem_paused = _make_dummy_reminder_dto(
        uuid7(), user_id, reminder_type=ReminderType.OPEN_TASK, status=ReminderStatus.PAUSED
    )
    kb_paused = build_reminder_detail_keyboard(rem_paused)
    assert kb_paused.inline_keyboard[0][0].text == "▶️ Відновити"
    assert kb_paused.inline_keyboard[1][0].text == "🗑 Видалити"


def test_wizard_quick_choice_keyboards() -> None:
    # 1. Відкриті справи
    kb_open = build_open_task_times_keyboard()
    assert len(kb_open.inline_keyboard) == 3
    cb_open = CreateWizardCallback.unpack(kb_open.inline_keyboard[0][0].callback_data or "")
    assert cb_open.step == "open_times"

    # 2. Річниці
    kb_anniv = build_anniversary_lead_times_keyboard()
    assert len(kb_anniv.inline_keyboard) == 3
    cb_anniv = CreateWizardCallback.unpack(kb_anniv.inline_keyboard[0][0].callback_data or "")
    assert cb_anniv.step == "anniv_leads"

    # 3. Дедлайн дати
    kb_dl_date = build_deadline_quick_date_keyboard()
    assert len(kb_dl_date.inline_keyboard) == 4
    cb_dl_date = CreateWizardCallback.unpack(kb_dl_date.inline_keyboard[0][0].callback_data or "")
    assert cb_dl_date.step == "dl_date"

    # 4. Дедлайн пріоритет
    kb_dl_prio = build_deadline_priority_keyboard()
    assert len(kb_dl_prio.inline_keyboard) == 3
    assert kb_dl_prio.inline_keyboard[0][0].text == "🤖 Автоматичний (динамична ескалація)"

    # 5. Підписка білінг
    kb_sub_bill = build_subscription_billing_keyboard()
    assert len(kb_sub_bill.inline_keyboard) == 4
    cb_sub_bill = CreateWizardCallback.unpack(kb_sub_bill.inline_keyboard[0][0].callback_data or "")
    assert cb_sub_bill.step == "sub_bill"

    # 6. Підписка режим
    kb_sub_mode = build_subscription_mode_keyboard()
    assert len(kb_sub_mode.inline_keyboard) == 3
    cb_sub_mode = CreateWizardCallback.unpack(kb_sub_mode.inline_keyboard[0][0].callback_data or "")
    assert cb_sub_mode.step == "sub_mode"

    # 7. Ліки графік
    kb_med_mode = build_medication_schedule_mode_keyboard()
    assert len(kb_med_mode.inline_keyboard) == 2
    cb_med_mode = CreateWizardCallback.unpack(kb_med_mode.inline_keyboard[0][0].callback_data or "")
    assert cb_med_mode.step == "med_mode"

    # 8. Ліки тривалість
    kb_med_dur = build_medication_duration_keyboard()
    assert len(kb_med_dur.inline_keyboard) == 2
    assert len(kb_med_dur.inline_keyboard[0]) == 3
    assert len(kb_med_dur.inline_keyboard[1]) == 3

    # 9. Ліки суворий графік
    kb_med_strict = build_medication_strict_keyboard()
    assert len(kb_med_strict.inline_keyboard) == 2
    cb_med_strict = CreateWizardCallback.unpack(kb_med_strict.inline_keyboard[0][0].callback_data or "")
    assert cb_med_strict.step == "med_strict"


# =============================================================================
# Тести Inline-клавіатур налаштувань
# =============================================================================


def test_build_settings_main_keyboard() -> None:
    user = _make_dummy_user_dto(uuid7())
    kb = build_settings_main_keyboard(user.settings)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 4
    assert "Автоескалація: Увімкнено ✅" in kb.inline_keyboard[3][0].text

    user.settings.auto_deadline_priority_escalation = False
    kb_disabled = build_settings_main_keyboard(user.settings)
    assert "Автоескалація: Вимкнено ❌" in kb_disabled.inline_keyboard[3][0].text


def test_build_bank_selection_keyboard() -> None:
    kb = build_bank_selection_keyboard("MONOBANK")
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 4
    # MONOBANK має бути виділений галочкою
    assert kb.inline_keyboard[0][0].text == "НБУ (Офіційний)"
    assert kb.inline_keyboard[1][0].text == "✅ Monobank (Картковий)"
    cb_bank = SettingsCallback.unpack(kb.inline_keyboard[1][0].callback_data or "")
    assert cb_bank.section == "bank"
    assert cb_bank.value == "MONOBANK"
    assert kb.inline_keyboard[2][0].text == "ПриватБанк (Картковий)"
    assert kb.inline_keyboard[3][0].text == "⬅️ Назад"


def test_build_quiet_hours_keyboard() -> None:
    kb = build_quiet_hours_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 5
    assert kb.inline_keyboard[0][0].text == "23:00 – 08:00"
    assert kb.inline_keyboard[3][0].text == "⌨️ Ввести власний час"
    assert kb.inline_keyboard[4][0].text == "⬅️ Назад"


def test_build_timezone_selection_keyboard() -> None:
    kb = build_timezone_selection_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 6
    assert kb.inline_keyboard[0][0].text == "🇺🇦 Europe/Kyiv"
    assert kb.inline_keyboard[4][0].text == "⌨️ Ввести вручну"
    assert kb.inline_keyboard[5][0].text == "⬅️ Назад"


# =============================================================================
# Тести Middlewares (Logging та Auth)
# =============================================================================


@pytest.mark.asyncio
async def test_bot_logging_middleware_message() -> None:
    middleware = BotLoggingMiddleware()
    user = User(id=999, is_bot=False, first_name="Тест")
    chat = Chat(id=999, type="private")
    message = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user, text="/help")

    handler_mock = AsyncMock(return_value="handler_result")
    result = await middleware(handler_mock, message, {})

    assert result == "handler_result"
    handler_mock.assert_awaited_once_with(message, {})


@pytest.mark.asyncio
async def test_bot_logging_middleware_callback_query() -> None:
    middleware = BotLoggingMiddleware()
    user = User(id=888, is_bot=False, first_name="Тест")
    cb = CallbackQuery(id="1", from_user=user, chat_instance="inst", data="cfg:menu:main")

    handler_mock = AsyncMock(return_value=123)
    result = await middleware(handler_mock, cb, {})

    assert result == 123
    handler_mock.assert_awaited_once_with(cb, {})


@pytest.mark.asyncio
async def test_bot_logging_middleware_exception() -> None:
    middleware = BotLoggingMiddleware()
    user = User(id=777, is_bot=False, first_name="Тест")
    chat = Chat(id=777, type="private")
    message = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user, text="fail")

    handler_mock = AsyncMock(side_effect=RuntimeError("Test error"))
    with pytest.raises(RuntimeError, match="Test error"):
        await middleware(handler_mock, message, {})


@pytest.mark.asyncio
async def test_bot_auth_middleware_message_success() -> None:
    api_client_mock = AsyncMock(spec=BackendApiClient)
    dummy_user = _make_dummy_user_dto(uuid7(), tg_id=555)
    api_client_mock.sync_telegram_user.return_value = dummy_user

    middleware = BotAuthMiddleware(api_client=api_client_mock)
    user = User(id=555, is_bot=False, first_name="Олексій", username="alex")
    chat = Chat(id=555, type="private")
    message = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user, text="/start")

    handler_mock = AsyncMock(return_value="ok")
    data: dict[str, object] = {}

    result = await middleware(handler_mock, message, data)
    assert result == "ok"
    api_client_mock.sync_telegram_user.assert_awaited_once()
    assert data["current_user"] == dummy_user
    assert data["api_client"] == api_client_mock


@pytest.mark.asyncio
async def test_bot_auth_middleware_callback_query_success() -> None:
    api_client_mock = AsyncMock(spec=BackendApiClient)
    dummy_user = _make_dummy_user_dto(uuid7(), tg_id=444)
    api_client_mock.sync_telegram_user.return_value = dummy_user

    middleware = BotAuthMiddleware()
    user = User(id=444, is_bot=False, first_name="Марія")
    chat = Chat(id=444, type="private")
    msg = Message(message_id=2, date=datetime.now(UTC), chat=chat, from_user=user, text="test")
    cb = CallbackQuery(id="2", from_user=user, chat_instance="inst", message=msg, data="cfg:menu:main")

    handler_mock = AsyncMock(return_value="cb_ok")
    data: dict[str, object] = {"api_client": api_client_mock}

    result = await middleware(handler_mock, cb, data)
    assert result == "cb_ok"
    api_client_mock.sync_telegram_user.assert_awaited_once()
    assert data["current_user"] == dummy_user


@pytest.mark.asyncio
async def test_bot_auth_middleware_no_api_client_raises() -> None:
    middleware = BotAuthMiddleware()
    user = User(id=111, is_bot=False, first_name="Тест")
    chat = Chat(id=111, type="private")
    message = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user, text="hi")

    with pytest.raises(RuntimeError, match="BackendApiClient is required"):
        await middleware(AsyncMock(), message, {})


@pytest.mark.asyncio
async def test_bot_auth_middleware_no_from_user() -> None:
    api_client_mock = AsyncMock(spec=BackendApiClient)
    middleware = BotAuthMiddleware(api_client=api_client_mock)
    chat = Chat(id=111, type="private")
    message = Message(message_id=1, date=datetime.now(UTC), chat=chat, text="no user")

    handler_mock = AsyncMock(return_value="pass")
    data: dict[str, object] = {}
    result = await middleware(handler_mock, message, data)
    assert result == "pass"
    api_client_mock.sync_telegram_user.assert_not_called()


# =============================================================================
# Тести RedisNotificationConsumer
# =============================================================================


@pytest.mark.asyncio
async def test_consumer_process_one_success() -> None:
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    rem_id = uuid7()
    payload = NotificationPayload(
        event_type=NotificationEventType.REMINDER_DUE,
        recipient_chat_id=123456,
        reminder_id=rem_id,
        reminder_type=ReminderType.OPEN_TASK,
        title="Час пити каву!",
        disable_sound=False,
    )
    raw_json = payload.model_dump_json()

    result = await consumer.process_one(raw_json)
    assert result is True
    bot_mock.send_message.assert_awaited_once()
    call_kwargs = bot_mock.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 123456
    assert "📋 <b>Нагадування про справу: Час пити каву!</b>" in call_kwargs["text"]
    assert isinstance(call_kwargs["reply_markup"], InlineKeyboardMarkup)
    assert call_kwargs["disable_notification"] is False


@pytest.mark.asyncio
async def test_consumer_process_one_invalid_json() -> None:
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    result = await consumer.process_one("invalid-json")
    assert result is False
    bot_mock.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_process_one_retry_after() -> None:
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    payload = NotificationPayload(recipient_chat_id=123, title="T")
    raw_json = payload.model_dump_json()

    req = SendMessage(chat_id=123, text="B")
    retry_exc = TelegramRetryAfter(method=req, message="Flood wait", retry_after=0)

    # Перший виклик кидає RetryAfter, другий успішний
    bot_mock.send_message.side_effect = [retry_exc, MagicMock()]

    result = await consumer.process_one(raw_json)
    assert result is True
    assert bot_mock.send_message.call_count == 2


@pytest.mark.asyncio
async def test_consumer_process_one_retry_after_second_failure() -> None:
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    payload = NotificationPayload(recipient_chat_id=123, title="T")
    raw_json = payload.model_dump_json()

    req = SendMessage(chat_id=123, text="B")
    retry_exc = TelegramRetryAfter(method=req, message="Flood wait", retry_after=0)

    bot_mock.send_message.side_effect = [retry_exc, RuntimeError("Failed again")]

    result = await consumer.process_one(raw_json)
    assert result is False
    assert bot_mock.send_message.call_count == 2


@pytest.mark.asyncio
async def test_consumer_process_one_forbidden() -> None:
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    payload = NotificationPayload(recipient_chat_id=123, title="T")
    raw_json = payload.model_dump_json()

    req = SendMessage(chat_id=123, text="B")
    bot_mock.send_message.side_effect = TelegramForbiddenError(method=req, message="Bot was blocked")

    result = await consumer.process_one(raw_json)
    assert result is False
    redis_mock.rpush.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_process_one_network_error_requeues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    payload = NotificationPayload(recipient_chat_id=123, title="T")
    raw_json = payload.model_dump_json()

    req = SendMessage(chat_id=123, text="B")
    bot_mock.send_message.side_effect = TelegramNetworkError(method=req, message="Timeout")

    result = await consumer.process_one(raw_json)
    assert result is False
    redis_mock.rpush.assert_awaited_once_with(consumer._queue_key, raw_json)


@pytest.mark.asyncio
async def test_consumer_process_one_server_error_requeues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    payload = NotificationPayload(recipient_chat_id=123, title="T")
    raw_json = payload.model_dump_json()

    req = SendMessage(chat_id=123, text="B")
    bot_mock.send_message.side_effect = TelegramServerError(method=req, message="500 Internal")

    result = await consumer.process_one(raw_json)
    assert result is False
    redis_mock.rpush.assert_awaited_once_with(consumer._queue_key, raw_json)


@pytest.mark.asyncio
async def test_consumer_process_one_unexpected_error() -> None:
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock)

    payload = NotificationPayload(recipient_chat_id=123, title="T")
    raw_json = payload.model_dump_json()

    bot_mock.send_message.side_effect = ValueError("Unexpected issue")

    result = await consumer.process_one(raw_json)
    assert result is False
    redis_mock.rpush.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_lifecycle_start_stop() -> None:
    bot_mock = AsyncMock()
    redis_mock = AsyncMock()
    # brpop повертає сповіщення, а потім None
    payload = NotificationPayload(recipient_chat_id=123, title="T")
    redis_mock.brpop.side_effect = [("queue:notifications:telegram", payload.model_dump_json()), None]

    consumer = RedisNotificationConsumer(bot=bot_mock, redis_client=redis_mock, brpop_timeout=1)
    assert consumer.is_running is False

    await consumer.start()
    assert consumer.is_running is True

    # Повторний start() не викликає помилки
    await consumer.start()

    # Даємо циклу виконати ітерацію
    await asyncio.sleep(0.05)

    await consumer.stop()
    assert consumer.is_running is False

    # Повторний stop() безпечний
    await consumer.stop()
    bot_mock.send_message.assert_awaited()
