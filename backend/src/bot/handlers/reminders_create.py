from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks.data import CreateReminderTypeCallback, CreateWizardCallback
from src.bot.client.api_client import BackendApiClient
from src.bot.formatters.messages import format_reminder_detail_message
from src.bot.keyboards import (
    BTN_CREATE_REMINDER,
    build_anniversary_lead_times_keyboard,
    build_cancel_reply_keyboard,
    build_create_reminder_type_keyboard,
    build_deadline_priority_keyboard,
    build_deadline_quick_date_keyboard,
    build_main_reply_keyboard,
    build_medication_duration_keyboard,
    build_medication_schedule_mode_keyboard,
    build_medication_strict_keyboard,
    build_open_task_times_keyboard,
    build_subscription_billing_keyboard,
    build_subscription_mode_keyboard,
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
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.domain.value_objects import (
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    ExactDateTimeDeadlineConfig,
    IntervalHoursConfig,
    LeadTimes,
)
from src.modules.users.queries.dto import UserResponseDTO

reminders_create_router = Router(name="reminders_create")


# =============================================================================
# Допоміжні функції валідації та парсингу
# =============================================================================


def _extract_user_info(
    event: Message | CallbackQuery,
    current_user: UserResponseDTO,
) -> tuple[int, str]:
    """Витягує Telegram ID та часовий пояс користувача."""
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (event.from_user.id if event.from_user else 0)
    )
    user_tz = current_user.settings.timezone
    return telegram_id, user_tz


def _parse_times_list(raw_text: str) -> list[time] | None:
    """
    Парсить рядок зі списком годин через кому або крапку з комою.

    Підтримує формати 'ГГ:ХХ' та 'Г:ХХ'. Повертає відсортований список time або None при помилці.
    """
    clean = raw_text.replace(";", ",")
    parts = [t.strip() for t in clean.split(",") if t.strip()]
    if not parts:
        return None

    parsed_times: list[time] = []
    for token in parts:
        sub = token.split(":")
        if len(sub) != 2:
            return None
        try:
            h = int(sub[0])
            m = int(sub[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                return None
            parsed_times.append(time(h, m))
        except ValueError:
            return None

    return sorted(list(set(parsed_times)))


def _parse_anniversary_date(raw_text: str) -> tuple[int, int, int | None] | None:
    """
    Парсить дату річниці у форматі ДД.ММ або ДД.ММ.РРРР.

    Повертає кортеж (day, month, birth_year) або None у разі невалідної дати.
    """
    clean = raw_text.strip().replace("/", ".").replace("-", ".")
    parts = clean.split(".")
    if len(parts) not in (2, 3):
        return None

    try:
        day = int(parts[0])
        month = int(parts[1])
        birth_year = int(parts[2]) if len(parts) == 3 else None
    except ValueError:
        return None

    if not (1 <= month <= 12):
        return None
    if not (1 <= day <= 31):
        return None
    if birth_year is not None and not (1900 <= birth_year <= 2100):
        return None

    # Перевірка на реальне існування календарної дати (використовуємо 2024 рік як високосний)
    test_year = birth_year if birth_year is not None else 2024
    try:
        date(test_year, month, day)
    except ValueError:
        return None

    return day, month, birth_year


def _parse_lead_times(raw_text: str) -> list[str] | None:
    """
    Парсить рядок завчасних нагадувань у список канонічних інтервалів.

    Повертає відсортований за спаданням список або None при помилці.
    """
    clean = raw_text.replace(";", ",")
    tokens = [t.strip() for t in clean.split(",") if t.strip()]
    if not tokens:
        return None
    try:
        lt = LeadTimes(tokens)
        res = lt.to_list()
        return res if res else None
    except Exception:
        return None


def _parse_amount_and_currency(raw_text: str) -> tuple[Decimal, CurrencyCode] | None:
    """
    Парсить рядок суми та валюти (наприклад '9.99 USD', '350 UAH' або '400').

    За замовчуванням встановлює валюту UAH. Повертає None при помилці або сумі <= 0.
    """
    clean = raw_text.strip().replace(",", ".")
    parts = clean.split()
    if not parts:
        return None

    try:
        amount = Decimal(parts[0])
        if amount <= Decimal("0.00"):
            return None
    except Exception:
        return None

    curr_str = parts[1].upper() if len(parts) > 1 else "UAH"
    if curr_str not in ("UAH", "USD", "EUR"):
        return None

    return amount, CurrencyCode(curr_str)


# =============================================================================
# Точка входу: початок створення нагадування (/new або кнопка)
# =============================================================================


@reminders_create_router.message(Command("new"), StateFilter("*"))
@reminders_create_router.message(F.text == BTN_CREATE_REMINDER, StateFilter("*"))
async def handle_new_reminder(message: Message, state: FSMContext) -> None:
    """
    Початок майстра створення нагадування: вибір одного з 5 підтримуваних типів.
    """
    await state.clear()
    await message.answer(
        "➕ <b>Оберіть тип нагадування, яке бажаєте створити:</b>",
        reply_markup=build_create_reminder_type_keyboard(),
    )


@reminders_create_router.callback_query(CreateReminderTypeCallback.filter())
async def handle_reminder_type_selection(
    callback: CallbackQuery,
    callback_data: CreateReminderTypeCallback,
    state: FSMContext,
) -> None:
    """
    Обробка вибору типу нагадування: перехід до відповідного FSM-майстра.
    """
    await state.clear()
    r_type = callback_data.reminder_type

    if r_type == ReminderType.OPEN_TASK.value:
        await state.set_state(OpenTaskCreateStates.waiting_for_title)
        prompt = (
            "📝 <b>Створення відкритої справи</b>\n\n"
            "Введіть назву справи або завдання:\n"
            "<i>(наприклад: Записатися до стоматолога)</i>"
        )
    elif r_type == ReminderType.ANNIVERSARY.value:
        await state.set_state(AnniversaryCreateStates.waiting_for_title)
        prompt = (
            "🎂 <b>Створення річниці або свята</b>\n\nВведіть назву події:\n<i>(наприклад: День народження мами)</i>"
        )
    elif r_type == ReminderType.DEADLINE_TASK.value:
        await state.set_state(DeadlineTaskCreateStates.waiting_for_title)
        prompt = (
            "🔥 <b>Створення задачі з дедлайном</b>\n\n"
            "Введіть назву задачі:\n"
            "<i>(наприклад: Здати квартальний звіт)</i>"
        )
    elif r_type == ReminderType.SUBSCRIPTION.value:
        await state.set_state(SubscriptionCreateStates.waiting_for_title)
        prompt = (
            "💳 <b>Створення підписки або регулярного платежу</b>\n\n"
            "Введіть назву сервісу або платежу:\n"
            "<i>(наприклад: Spotify, Netflix, Оренда)</i>"
        )
    elif r_type == ReminderType.MEDICATION.value:
        await state.set_state(MedicationCreateStates.waiting_for_title)
        prompt = (
            "💊 <b>Створення нагадування про прийом ліків</b>\n\n"
            "Введіть назву лікарського засобу та дозування:\n"
            "<i>(наприклад: Амоксиклав 1000 мг)</i>"
        )
    else:
        await callback.answer("Невідомий тип нагадування.", show_alert=True)
        return

    if isinstance(callback.message, Message):
        await callback.message.answer(
            prompt,
            reply_markup=build_cancel_reply_keyboard(),
        )
    await callback.answer()


# =============================================================================
# Майстер 1: OPEN_TASK (Відкрита справа)
# =============================================================================


@reminders_create_router.message(OpenTaskCreateStates.waiting_for_title, F.text)
async def handle_open_task_title(message: Message, state: FSMContext) -> None:
    """Обробка назви відкритої справи."""
    title = (message.text or "").strip()
    if not (1 <= len(title) <= 255):
        await message.answer("⚠️ Назва справи повинна містити від 1 до 255 символів. Будь ласка, введіть назву:")
        return

    await state.update_data(title=title)
    await state.set_state(OpenTaskCreateStates.waiting_for_times)
    await message.answer(
        "⏰ <b>Оберіть графік щоденних нагадувань</b> або введіть години через кому "
        "(наприклад, <code>09:00, 15:00</code>):",
        reply_markup=build_open_task_times_keyboard(),
    )


@reminders_create_router.callback_query(
    OpenTaskCreateStates.waiting_for_times,
    CreateWizardCallback.filter(F.step == "open_times"),
)
async def handle_open_task_times_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка вибору графіка відкритої справи через інлайн-кнопку."""
    parsed_times = _parse_times_list(callback_data.value)
    if not parsed_times:
        await callback.answer("Некоректний час.", show_alert=True)
        return

    data = await state.get_data()
    title = data.get("title", "")
    telegram_id, user_tz = _extract_user_info(callback, current_user)

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.OPEN_TASK,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title=title,
        schedule_config=DailyAtTimesConfig(times=parsed_times).to_dict(),
        lead_times=[],
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Відкриту справу створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    if isinstance(callback.message, Message):
        await callback.message.answer(msg_text, reply_markup=build_main_reply_keyboard())
    await callback.answer("✅ Створено!")


@reminders_create_router.message(OpenTaskCreateStates.waiting_for_times, F.text)
async def handle_open_task_times_message(
    message: Message,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка ручного введення годин щоденних нагадувань для відкритої справи."""
    parsed_times = _parse_times_list(message.text or "")
    if not parsed_times:
        await message.answer(
            "⚠️ Некоректний формат годин. Введіть години у форматі ГГ:ХХ через кому "
            "(наприклад, <code>09:00, 15:00</code>):"
        )
        return

    data = await state.get_data()
    title = data.get("title", "")
    telegram_id, user_tz = _extract_user_info(message, current_user)

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.OPEN_TASK,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title=title,
        schedule_config=DailyAtTimesConfig(times=parsed_times).to_dict(),
        lead_times=[],
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Відкриту справу створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    await message.answer(msg_text, reply_markup=build_main_reply_keyboard())


# =============================================================================
# Майстер 2: ANNIVERSARY (Річниця або день народження)
# =============================================================================


@reminders_create_router.message(AnniversaryCreateStates.waiting_for_title, F.text)
async def handle_anniversary_title(message: Message, state: FSMContext) -> None:
    """Обробка назви річниці або пам'ятної події."""
    title = (message.text or "").strip()
    if not (1 <= len(title) <= 255):
        await message.answer("⚠️ Назва події повинна містити від 1 до 255 символів. Будь ласка, введіть назву:")
        return

    await state.update_data(title=title)
    await state.set_state(AnniversaryCreateStates.waiting_for_date)
    await message.answer(
        "📅 <b>Введіть дату події</b> у форматі <code>ДД.ММ</code> або <code>ДД.ММ.РРРР</code> "
        "(наприклад, <code>15.05</code> або <code>15.05.1995</code>):"
    )


@reminders_create_router.message(AnniversaryCreateStates.waiting_for_date, F.text)
async def handle_anniversary_date(message: Message, state: FSMContext) -> None:
    """Обробка дати річниці (день, місяць, опціональний рік народження)."""
    parsed = _parse_anniversary_date(message.text or "")
    if not parsed:
        await message.answer(
            "⚠️ Некоректний формат дати. Будь ласка, введіть дату у форматі <code>ДД.ММ</code> "
            "або <code>ДД.ММ.РРРР</code> (наприклад, <code>15.05</code> або <code>15.05.1995</code>):"
        )
        return

    day, month, birth_year = parsed
    await state.update_data(day=day, month=month, birth_year=birth_year)
    await state.set_state(AnniversaryCreateStates.waiting_for_lead_times)
    await message.answer(
        "🔔 <b>Оберіть каскад завчасних нагадувань</b> або введіть власний через кому "
        "(наприклад, <code>14d, 7d, 3d, 1d, 0d</code>):",
        reply_markup=build_anniversary_lead_times_keyboard(),
    )


@reminders_create_router.callback_query(
    AnniversaryCreateStates.waiting_for_lead_times,
    CreateWizardCallback.filter(F.step == "anniv_leads"),
)
async def handle_anniversary_leads_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка вибору каскаду завчасних нагадувань річниці через інлайн-кнопку."""
    lead_times_list = _parse_lead_times(callback_data.value)
    if not lead_times_list:
        await callback.answer("Некоректний формат інтервалів.", show_alert=True)
        return

    data = await state.get_data()
    title = data.get("title", "")
    day = int(data.get("day", 1))
    month = int(data.get("month", 1))
    birth_year = data.get("birth_year")

    telegram_id, user_tz = _extract_user_info(callback, current_user)

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.ANNIVERSARY,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title=title,
        schedule_config=DateWithMonthIntervalConfig(
            day=day,
            month=month,
            interval_months=12,
            birth_year=birth_year,
        ).to_dict(),
        lead_times=lead_times_list,
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Річницю успішно створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    if isinstance(callback.message, Message):
        await callback.message.answer(msg_text, reply_markup=build_main_reply_keyboard())
    await callback.answer("✅ Створено!")


@reminders_create_router.message(AnniversaryCreateStates.waiting_for_lead_times, F.text)
async def handle_anniversary_leads_message(
    message: Message,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка ручного введення каскаду завчасних нагадувань річниці."""
    lead_times_list = _parse_lead_times(message.text or "")
    if not lead_times_list:
        await message.answer(
            "⚠️ Некоректний формат завчасних нагадувань. Використовуйте одиниці d (дні), "
            "w (тижні), h (години), m (хвилини), наприклад: <code>14d, 7d, 1d, 0d</code>:"
        )
        return

    data = await state.get_data()
    title = data.get("title", "")
    day = int(data.get("day", 1))
    month = int(data.get("month", 1))
    birth_year = data.get("birth_year")

    telegram_id, user_tz = _extract_user_info(message, current_user)

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.ANNIVERSARY,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title=title,
        schedule_config=DateWithMonthIntervalConfig(
            day=day,
            month=month,
            interval_months=12,
            birth_year=birth_year,
        ).to_dict(),
        lead_times=lead_times_list,
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Річницю успішно створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    await message.answer(msg_text, reply_markup=build_main_reply_keyboard())


# =============================================================================
# Майстер 3: DEADLINE_TASK (Задача з дедлайном)
# =============================================================================


@reminders_create_router.message(DeadlineTaskCreateStates.waiting_for_title, F.text)
async def handle_deadline_title(message: Message, state: FSMContext) -> None:
    """Обробка назви задачі з дедлайном."""
    title = (message.text or "").strip()
    if not (1 <= len(title) <= 255):
        await message.answer("⚠️ Назва задачі повинна містити від 1 до 255 символів. Будь ласка, введіть назву:")
        return

    await state.update_data(title=title)
    await state.set_state(DeadlineTaskCreateStates.waiting_for_deadline)
    await message.answer(
        "🚨 <b>Оберіть або введіть дату та час дедлайну</b> у форматі <code>ДД.ММ.РРРР ГГ:ХХ</code> "
        "(наприклад, <code>25.12.2026 18:00</code>):",
        reply_markup=build_deadline_quick_date_keyboard(),
    )


@reminders_create_router.callback_query(
    DeadlineTaskCreateStates.waiting_for_deadline,
    CreateWizardCallback.filter(F.step == "dl_date"),
)
async def handle_deadline_date_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
) -> None:
    """Обробка швидкого вибору дедлайну через інлайн-кнопку."""
    _, user_tz = _extract_user_info(callback, current_user)
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)
    choice = callback_data.value

    if choice == "today_18":
        target = now_local.replace(hour=18, minute=0, second=0, microsecond=0)
        if target <= now_local:
            target += timedelta(days=1)
    elif choice == "tomorrow_12":
        target = (now_local + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    elif choice == "tomorrow_18":
        target = (now_local + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    elif choice == "in3days_18":
        target = (now_local + timedelta(days=3)).replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        await callback.answer("Невідомий варіант дати.", show_alert=True)
        return

    due_dt_utc = target.astimezone(UTC)
    await state.update_data(due_datetime_iso=due_dt_utc.isoformat())
    await state.set_state(DeadlineTaskCreateStates.waiting_for_priority)

    if isinstance(callback.message, Message):
        await callback.message.answer(
            "🎯 <b>Оберіть пріоритет задачі:</b>",
            reply_markup=build_deadline_priority_keyboard(),
        )
    await callback.answer()


@reminders_create_router.message(DeadlineTaskCreateStates.waiting_for_deadline, F.text)
async def handle_deadline_date_message(
    message: Message,
    state: FSMContext,
    current_user: UserResponseDTO,
) -> None:
    """Обробка ручного введення дати та часу дедлайну у таймзоні користувача."""
    _, user_tz = _extract_user_info(message, current_user)
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("UTC")

    clean_text = " ".join((message.text or "").strip().replace(",", " ").split())
    try:
        parsed_dt = datetime.strptime(clean_text, "%d.%m.%Y %H:%M")
        target = parsed_dt.replace(tzinfo=tz)
    except Exception:
        await message.answer(
            "⚠️ Некоректний формат дати та часу. Введіть дату у форматі <code>ДД.ММ.РРРР ГГ:ХХ</code> "
            "(наприклад, <code>25.12.2026 18:00</code>):"
        )
        return

    now_local = datetime.now(tz)
    if target <= now_local:
        await message.answer("⚠️ Дата і час дедлайну повинні бути у майбутньому. Будь ласка, вкажіть майбутню дату:")
        return

    due_dt_utc = target.astimezone(UTC)
    await state.update_data(due_datetime_iso=due_dt_utc.isoformat())
    await state.set_state(DeadlineTaskCreateStates.waiting_for_priority)
    await message.answer(
        "🎯 <b>Оберіть пріоритет задачі:</b>",
        reply_markup=build_deadline_priority_keyboard(),
    )


@reminders_create_router.callback_query(
    DeadlineTaskCreateStates.waiting_for_priority,
    CreateWizardCallback.filter(F.step == "dl_prio"),
)
async def handle_deadline_priority_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка вибору пріоритету або автоматичної ескалації дедлайну."""
    prio_val = callback_data.value
    base_priority: Priority | None = None
    if prio_val != "AUTO":
        try:
            base_priority = Priority(prio_val)
        except ValueError:
            await callback.answer("Невідомий пріоритет.", show_alert=True)
            return

    data = await state.get_data()
    title = data.get("title", "")
    due_iso = data.get("due_datetime_iso")
    if not due_iso:
        await callback.answer("Дані дедлайну застаріли. Почніть знову.", show_alert=True)
        await state.clear()
        return

    due_dt_utc = datetime.fromisoformat(due_iso)
    telegram_id, user_tz = _extract_user_info(callback, current_user)

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.DEADLINE_TASK,
        schedule_logic=ScheduleLogicType.EXACT_DATETIME_DEADLINE,
        title=title,
        schedule_config=ExactDateTimeDeadlineConfig(due_datetime=due_dt_utc).to_dict(),
        lead_times=["1d", "2h", "0d"],
        due_datetime=due_dt_utc,
        base_priority=base_priority,
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Задачу з дедлайном створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    if isinstance(callback.message, Message):
        await callback.message.answer(msg_text, reply_markup=build_main_reply_keyboard())
    await callback.answer("✅ Створено!")


# =============================================================================
# Майстер 4: SUBSCRIPTION (Підписка / Оренда)
# =============================================================================


@reminders_create_router.message(SubscriptionCreateStates.waiting_for_title, F.text)
async def handle_subscription_title(message: Message, state: FSMContext) -> None:
    """Обробка назви підписки або регулярного платежу."""
    title = (message.text or "").strip()
    if not (1 <= len(title) <= 255):
        await message.answer("⚠️ Назва підписки повинна містити від 1 до 255 символів. Будь ласка, введіть назву:")
        return

    await state.update_data(title=title)
    await state.set_state(SubscriptionCreateStates.waiting_for_amount_currency)
    await message.answer(
        "💰 <b>Введіть суму та валюту регулярного платежу</b> (наприклад: <code>9.99 USD</code>, "
        "<code>4.99 EUR</code> або <code>350 UAH</code>, якщо тільки цифра — за замовчуванням <code>UAH</code>):"
    )


@reminders_create_router.message(SubscriptionCreateStates.waiting_for_amount_currency, F.text)
async def handle_subscription_amount_currency(message: Message, state: FSMContext) -> None:
    """Обробка суми та валюти розрахунку підписки."""
    parsed = _parse_amount_and_currency(message.text or "")
    if not parsed:
        await message.answer(
            "⚠️ Некоректна сума або валюта. Введіть число більше 0 та валюту (UAH, USD, EUR), "
            "наприклад: <code>9.99 USD</code> або <code>350 UAH</code>:"
        )
        return

    amount, currency = parsed
    await state.update_data(regular_amount=str(amount), currency=currency.value)
    await state.set_state(SubscriptionCreateStates.waiting_for_billing_day)
    await message.answer(
        "📅 <b>Оберіть день списання коштів</b> або введіть число місяця (<code>1–31</code>):",
        reply_markup=build_subscription_billing_keyboard(),
    )


@reminders_create_router.callback_query(
    SubscriptionCreateStates.waiting_for_billing_day,
    CreateWizardCallback.filter(F.step == "sub_bill"),
)
async def handle_subscription_billing_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
) -> None:
    """Обробка швидкого вибору дня розрахункового циклу підписки через інлайн-кнопку."""
    _, user_tz = _extract_user_info(callback, current_user)
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("UTC")

    val = callback_data.value
    if val == "today_1":
        day = datetime.now(tz).day
        interval_months = 1
    elif val == "today_12":
        day = datetime.now(tz).day
        interval_months = 12
    elif val == "1_1":
        day = 1
        interval_months = 1
    elif val == "15_1":
        day = 15
        interval_months = 1
    else:
        parts = val.split("_")
        try:
            day = int(parts[0])
            interval_months = int(parts[1]) if len(parts) > 1 else 1
        except (ValueError, IndexError):
            await callback.answer("Некоректний день.", show_alert=True)
            return

    await state.update_data(billing_day=day, interval_months=interval_months)
    await state.set_state(SubscriptionCreateStates.waiting_for_mode)

    if isinstance(callback.message, Message):
        await callback.message.answer(
            "💳 <b>Оберіть режим підписки:</b>",
            reply_markup=build_subscription_mode_keyboard(),
        )
    await callback.answer()


@reminders_create_router.message(SubscriptionCreateStates.waiting_for_billing_day, F.text)
async def handle_subscription_billing_message(
    message: Message,
    state: FSMContext,
) -> None:
    """Обробка ручного введення дня місяця для розрахунків за підпискою."""
    try:
        day = int((message.text or "").strip())
        if not (1 <= day <= 31):
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Некоректний день місяця. Введіть число від 1 до 31:")
        return

    await state.update_data(billing_day=day, interval_months=1)
    await state.set_state(SubscriptionCreateStates.waiting_for_mode)
    await message.answer(
        "💳 <b>Оберіть режим підписки:</b>",
        reply_markup=build_subscription_mode_keyboard(),
    )


@reminders_create_router.callback_query(
    SubscriptionCreateStates.waiting_for_mode,
    CreateWizardCallback.filter(F.step == "sub_mode"),
)
async def handle_subscription_mode_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка вибору режиму підписки: звичайна, безкоштовний пробний період або знижка."""
    mode = callback_data.value

    if mode == "regular":
        data = await state.get_data()
        title = data.get("title", "")
        amount = Decimal(data.get("regular_amount", "0"))
        currency = CurrencyCode(data.get("currency", "UAH"))
        day = int(data.get("billing_day", 1))
        interval_months = int(data.get("interval_months", 1))

        telegram_id, user_tz = _extract_user_info(callback, current_user)

        cmd = CreateReminderCommand(
            reminder_type=ReminderType.SUBSCRIPTION,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            title=title,
            schedule_config=DateWithMonthIntervalConfig(
                day=day,
                interval_months=interval_months,
            ).to_dict(),
            lead_times=["3d", "1d", "0d"],
            regular_amount=amount,
            currency=currency,
            is_trial=False,
        )
        created = await api_client.create_reminder(telegram_id, cmd)
        await state.clear()

        msg_text = "✅ <b>Підписку успішно створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
        if isinstance(callback.message, Message):
            await callback.message.answer(msg_text, reply_markup=build_main_reply_keyboard())
        await callback.answer("✅ Створено!")

    elif mode == "trial":
        await state.set_state(SubscriptionCreateStates.waiting_for_trial_date)
        prompt = (
            "🎁 <b>Введіть дату закінчення безкоштовного пробного періоду (Trial)</b> "
            "у форматі <code>ДД.ММ.РРРР</code>:"
        )
        if isinstance(callback.message, Message):
            await callback.message.answer(prompt, reply_markup=build_cancel_reply_keyboard())
        await callback.answer()

    elif mode == "discount":
        await state.set_state(SubscriptionCreateStates.waiting_for_discount_details)
        prompt = (
            "🏷 <b>Введіть акційну ціну та кількість пільгових циклів</b> через пробіл "
            "(наприклад: <code>1.99 3</code> — 1.99 у вашій валюті на 3 цикли):"
        )
        if isinstance(callback.message, Message):
            await callback.message.answer(prompt, reply_markup=build_cancel_reply_keyboard())
        await callback.answer()

    else:
        await callback.answer("Невідомий режим підписки.", show_alert=True)


@reminders_create_router.message(SubscriptionCreateStates.waiting_for_trial_date, F.text)
async def handle_subscription_trial_date(
    message: Message,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка дати завершення пробного періоду (Trial) підписки."""
    telegram_id, user_tz = _extract_user_info(message, current_user)
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("UTC")

    clean = (message.text or "").strip().replace("/", ".").replace("-", ".")
    try:
        trial_date = datetime.strptime(clean, "%d.%m.%Y").date()
    except Exception:
        await message.answer(
            "⚠️ Некоректний формат дати. Введіть дату у форматі <code>ДД.ММ.РРРР</code> "
            "(наприклад, <code>25.12.2026</code>):"
        )
        return

    today = datetime.now(tz).date()
    if trial_date <= today:
        await message.answer(
            "⚠️ Дата закінчення пробного періоду повинна бути у майбутньому. Будь ласка, введіть майбутню дату:"
        )
        return

    data = await state.get_data()
    title = data.get("title", "")
    amount = Decimal(data.get("regular_amount", "0"))
    currency = CurrencyCode(data.get("currency", "UAH"))
    day = int(data.get("billing_day", 1))
    interval_months = int(data.get("interval_months", 1))

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.SUBSCRIPTION,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title=title,
        schedule_config=DateWithMonthIntervalConfig(
            day=day,
            interval_months=interval_months,
        ).to_dict(),
        lead_times=["3d", "1d", "0d"],
        regular_amount=amount,
        currency=currency,
        is_trial=True,
        trial_end_date=trial_date,
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Підписку з пробним періодом створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    await message.answer(msg_text, reply_markup=build_main_reply_keyboard())


@reminders_create_router.message(SubscriptionCreateStates.waiting_for_discount_details, F.text)
async def handle_subscription_discount_details(
    message: Message,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка деталей акційної знижки (пільгова сума та кількість циклів)."""
    parts = (message.text or "").strip().replace(",", ".").split()
    if len(parts) != 2:
        await message.answer(
            "⚠️ Некоректний формат. Введіть акційну ціну та кількість циклів через пробіл "
            "(наприклад: <code>1.99 3</code>):"
        )
        return

    try:
        discount_amount = Decimal(parts[0])
        cycles = int(parts[1])
        if discount_amount < Decimal("0.00") or cycles <= 0:
            raise ValueError
    except Exception:
        await message.answer(
            "⚠️ Некоректні значення. Ціна має бути невід'ємною, а кількість циклів — "
            "цілим додатним числом (наприклад: <code>1.99 3</code>):"
        )
        return

    data = await state.get_data()
    title = data.get("title", "")
    amount = Decimal(data.get("regular_amount", "0"))
    currency = CurrencyCode(data.get("currency", "UAH"))
    day = int(data.get("billing_day", 1))
    interval_months = int(data.get("interval_months", 1))

    telegram_id, user_tz = _extract_user_info(message, current_user)

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.SUBSCRIPTION,
        schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
        title=title,
        schedule_config=DateWithMonthIntervalConfig(
            day=day,
            interval_months=interval_months,
        ).to_dict(),
        lead_times=["3d", "1d", "0d"],
        regular_amount=amount,
        currency=currency,
        is_trial=False,
        discount_amount=discount_amount,
        discount_cycles_total=cycles,
        discount_cycles_remaining=cycles,
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Підписку зі знижкою успішно створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    await message.answer(msg_text, reply_markup=build_main_reply_keyboard())


# =============================================================================
# Майстер 5: MEDICATION (Прийом ліків)
# =============================================================================


@reminders_create_router.message(MedicationCreateStates.waiting_for_title, F.text)
async def handle_medication_title(message: Message, state: FSMContext) -> None:
    """Обробка назви та дозування лікарського засобу."""
    title = (message.text or "").strip()
    if not (1 <= len(title) <= 255):
        await message.answer("⚠️ Назва препарату повинна містити від 1 до 255 символів. Будь ласка, введіть назву:")
        return

    await state.update_data(title=title)
    await state.set_state(MedicationCreateStates.waiting_for_schedule_mode)
    await message.answer(
        "⏰ <b>Як ви приймаєте цей препарат?</b>",
        reply_markup=build_medication_schedule_mode_keyboard(),
    )


@reminders_create_router.callback_query(
    MedicationCreateStates.waiting_for_schedule_mode,
    CreateWizardCallback.filter(F.step == "med_mode"),
)
async def handle_medication_schedule_mode(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
) -> None:
    """Обробка вибору типу розкладу ліків (щодня у фіксовані години або інтервал кожні N годин)."""
    sched_mode = callback_data.value
    await state.update_data(med_mode=sched_mode)
    await state.set_state(MedicationCreateStates.waiting_for_schedule_value)

    if sched_mode == "daily":
        prompt = "🕘 <b>Введіть години прийому через кому</b> (наприклад: <code>08:00, 14:00, 20:00</code>):"
    elif sched_mode == "interval":
        prompt = (
            "🔄 <b>Введіть інтервал у годинах</b> (число від <code>1</code> до <code>24</code>, "
            "наприклад <code>8</code> для прийому кожні 8 годин):"
        )
    else:
        await callback.answer("Невідомий режим прийому.", show_alert=True)
        return

    if isinstance(callback.message, Message):
        await callback.message.answer(prompt, reply_markup=build_cancel_reply_keyboard())
    await callback.answer()


@reminders_create_router.message(MedicationCreateStates.waiting_for_schedule_value, F.text)
async def handle_medication_schedule_value(message: Message, state: FSMContext) -> None:
    """Обробка значень розкладу прийому препарату."""
    data = await state.get_data()
    med_mode = data.get("med_mode")

    if med_mode == "daily":
        parsed_times = _parse_times_list(message.text or "")
        if not parsed_times:
            await message.answer(
                "⚠️ Некоректний формат годин. Введіть години через кому у форматі ГГ:ХХ "
                "(наприклад: <code>08:00, 14:00, 20:00</code>):"
            )
            return
        schedule_logic = ScheduleLogicType.DAILY_AT_TIMES
        schedule_config = DailyAtTimesConfig(times=parsed_times).to_dict()

    elif med_mode == "interval":
        try:
            interval_hours = int((message.text or "").strip())
            if not (1 <= interval_hours <= 24):
                raise ValueError
        except ValueError:
            await message.answer("⚠️ Некоректне значення інтервалу. Введіть ціле число від 1 до 24:")
            return
        schedule_logic = ScheduleLogicType.INTERVAL_HOURS
        schedule_config = IntervalHoursConfig(interval_hours=interval_hours).to_dict()

    else:
        await message.answer("⚠️ Помилка стану. Почніть створення спочатку командою /new.")
        await state.clear()
        return

    await state.update_data(
        schedule_logic=schedule_logic.value,
        schedule_config=schedule_config,
    )
    await state.set_state(MedicationCreateStates.waiting_for_duration)
    await message.answer(
        "📅 <b>Оберіть тривалість курсу прийому</b> або введіть кількість днів числом:",
        reply_markup=build_medication_duration_keyboard(),
    )


@reminders_create_router.callback_query(
    MedicationCreateStates.waiting_for_duration,
    CreateWizardCallback.filter(F.step == "med_dur"),
)
async def handle_medication_duration_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
) -> None:
    """Обробка швидкого вибору тривалості курсу ліків через інлайн-кнопку."""
    try:
        duration_days = int(callback_data.value)
        if duration_days < 0:
            raise ValueError
    except ValueError:
        await callback.answer("Некоректна тривалість.", show_alert=True)
        return

    _, user_tz = _extract_user_info(callback, current_user)
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("UTC")

    local_today = datetime.now(tz).date()
    if duration_days > 0:
        course_days = duration_days
        start_date_iso = local_today.isoformat()
        end_date_iso = (local_today + timedelta(days=duration_days - 1)).isoformat()
    else:
        course_days = None
        start_date_iso = None
        end_date_iso = None

    await state.update_data(
        course_duration_days=course_days,
        start_date=start_date_iso,
        end_date=end_date_iso,
    )
    await state.set_state(MedicationCreateStates.waiting_for_strict_mode)

    if isinstance(callback.message, Message):
        await callback.message.answer(
            "🛡 <b>Оберіть нічний режим прийому:</b>",
            reply_markup=build_medication_strict_keyboard(),
        )
    await callback.answer()


@reminders_create_router.message(MedicationCreateStates.waiting_for_duration, F.text)
async def handle_medication_duration_message(
    message: Message,
    state: FSMContext,
    current_user: UserResponseDTO,
) -> None:
    """Обробка ручного введення тривалості курсу ліків у днях."""
    try:
        duration_days = int((message.text or "").strip())
        if duration_days < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введіть додатне число днів або 0 для безстрокового курсу:")
        return

    _, user_tz = _extract_user_info(message, current_user)
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("UTC")

    local_today = datetime.now(tz).date()
    if duration_days > 0:
        course_days = duration_days
        start_date_iso = local_today.isoformat()
        end_date_iso = (local_today + timedelta(days=duration_days - 1)).isoformat()
    else:
        course_days = None
        start_date_iso = None
        end_date_iso = None

    await state.update_data(
        course_duration_days=course_days,
        start_date=start_date_iso,
        end_date=end_date_iso,
    )
    await state.set_state(MedicationCreateStates.waiting_for_strict_mode)
    await message.answer(
        "🛡 <b>Оберіть нічний режим прийому:</b>",
        reply_markup=build_medication_strict_keyboard(),
    )


@reminders_create_router.callback_query(
    MedicationCreateStates.waiting_for_strict_mode,
    CreateWizardCallback.filter(F.step == "med_strict"),
)
async def handle_medication_strict_callback(
    callback: CallbackQuery,
    callback_data: CreateWizardCallback,
    state: FSMContext,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """Обробка налаштування нічного режиму (тихих годин) та створення нагадування про ліки."""
    strict_schedule = callback_data.value == "true"

    data = await state.get_data()
    title = data.get("title", "")
    schedule_logic_str = data.get("schedule_logic")
    schedule_config = data.get("schedule_config")

    if not schedule_logic_str or not schedule_config:
        await callback.answer("Дані розкладу застаріли. Почніть знову.", show_alert=True)
        await state.clear()
        return

    schedule_logic = ScheduleLogicType(schedule_logic_str)
    course_days = data.get("course_duration_days")
    start_date = date.fromisoformat(data["start_date"]) if data.get("start_date") else None
    end_date = date.fromisoformat(data["end_date"]) if data.get("end_date") else None

    telegram_id, user_tz = _extract_user_info(callback, current_user)

    cmd = CreateReminderCommand(
        reminder_type=ReminderType.MEDICATION,
        schedule_logic=schedule_logic,
        title=title,
        schedule_config=schedule_config,
        lead_times=[],
        course_duration_days=course_days,
        medication_start_date=start_date,
        medication_end_date=end_date,
        strict_schedule=strict_schedule,
    )
    created = await api_client.create_reminder(telegram_id, cmd)
    await state.clear()

    msg_text = "✅ <b>Курс ліків успішно створено!</b>\n\n" + format_reminder_detail_message(created, user_tz)
    if isinstance(callback.message, Message):
        await callback.message.answer(msg_text, reply_markup=build_main_reply_keyboard())
    await callback.answer("✅ Створено!")
