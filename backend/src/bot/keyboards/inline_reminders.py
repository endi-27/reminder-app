from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.api.schemas.pagination import PaginatedResponse
from src.bot.callbacks.data import (
    CreateReminderTypeCallback,
    CreateWizardCallback,
    ReminderActionCallback,
    ReminderDetailCallback,
    ReminderListFilterCallback,
)
from src.infrastructure.notifications.dto import (
    NotificationEventType,
    NotificationPayload,
)
from src.modules.reminders.domain.enums import ReminderStatus, ReminderType
from src.modules.reminders.queries.dto import ReminderResponseDTO

CATEGORY_FILTER_BUTTONS: list[tuple[str, str]] = [
    ("ALL", "Усі"),
    ("ANNIVERSARY", "🎂"),
    ("OPEN_TASK", "📝"),
    ("DEADLINE_TASK", "🔥"),
    ("SUBSCRIPTION", "💳"),
    ("MEDICATION", "💊"),
]


def build_notification_keyboard(payload: NotificationPayload) -> InlineKeyboardMarkup | None:
    """Конвертація DTO сповіщення в інлайн-клавіатуру дій Telegram відповідно до типу події та нагадування."""
    if payload.event_type == NotificationEventType.DAILY_DIGEST:
        if not payload.digest_tasks:
            return None
        builder = InlineKeyboardBuilder()
        builder.button(
            text="📋 Відкрити мої справи",
            callback_data=ReminderListFilterCallback(category=ReminderType.OPEN_TASK.value, page=1).pack(),
        )
        builder.adjust(1)
        return builder.as_markup()

    if payload.reminder_id is None:
        return None

    builder = InlineKeyboardBuilder()

    if payload.event_type == NotificationEventType.TRIAL_EXPIRED:
        builder.button(
            text="💳 Оплачено",
            callback_data=ReminderActionCallback(action="payment", reminder_id=payload.reminder_id, minutes=0).pack(),
        )
        builder.button(
            text="❌ Скасувати підписку",
            callback_data=ReminderActionCallback(action="cancel", reminder_id=payload.reminder_id, minutes=0).pack(),
        )
        builder.adjust(2)
        return builder.as_markup()

    if payload.event_type == NotificationEventType.REMINDER_DUE:
        if payload.reminder_type == ReminderType.SUBSCRIPTION:
            builder.button(
                text="💳 Оплачено",
                callback_data=ReminderActionCallback(
                    action="payment", reminder_id=payload.reminder_id, minutes=0
                ).pack(),
            )
            builder.button(
                text="⏰ Нагадати завтра",
                callback_data=ReminderActionCallback(
                    action="snooze", reminder_id=payload.reminder_id, minutes=1440
                ).pack(),
            )
            builder.button(
                text="❌ Скасувати підписку",
                callback_data=ReminderActionCallback(
                    action="cancel", reminder_id=payload.reminder_id, minutes=0
                ).pack(),
            )
            builder.adjust(2, 1)
            return builder.as_markup()

        if payload.reminder_type == ReminderType.MEDICATION:
            builder.button(
                text="💊 Прийняв",
                callback_data=ReminderActionCallback(
                    action="med_taken", reminder_id=payload.reminder_id, minutes=0
                ).pack(),
            )
            builder.button(
                text="⏰ +15 хв",
                callback_data=ReminderActionCallback(
                    action="snooze", reminder_id=payload.reminder_id, minutes=15
                ).pack(),
            )
            builder.button(
                text="❌ Пропустив",
                callback_data=ReminderActionCallback(
                    action="med_missed", reminder_id=payload.reminder_id, minutes=0
                ).pack(),
            )
            builder.adjust(2, 1)
            return builder.as_markup()

        if payload.reminder_type == ReminderType.DEADLINE_TASK:
            builder.button(
                text="✅ Виконано",
                callback_data=ReminderActionCallback(
                    action="complete", reminder_id=payload.reminder_id, minutes=0
                ).pack(),
            )
            builder.button(
                text="⏰ +1 год",
                callback_data=ReminderActionCallback(
                    action="snooze", reminder_id=payload.reminder_id, minutes=60
                ).pack(),
            )
            builder.adjust(2)
            return builder.as_markup()

        if payload.reminder_type == ReminderType.ANNIVERSARY:
            builder.button(
                text="✅ Привітав",
                callback_data=ReminderActionCallback(
                    action="complete", reminder_id=payload.reminder_id, minutes=0
                ).pack(),
            )
            builder.adjust(1)
            return builder.as_markup()

        if payload.reminder_type == ReminderType.OPEN_TASK:
            builder.button(
                text="✅ Виконано",
                callback_data=ReminderActionCallback(
                    action="complete", reminder_id=payload.reminder_id, minutes=0
                ).pack(),
            )
            builder.button(
                text="⏰ Відкласти",
                callback_data=ReminderActionCallback(
                    action="snooze", reminder_id=payload.reminder_id, minutes=180
                ).pack(),
            )
            builder.adjust(2)
            return builder.as_markup()

    return None


def build_create_reminder_type_keyboard() -> InlineKeyboardMarkup:
    """Генерація клавіатури вибору одного з 5 типів нагадування."""
    builder = InlineKeyboardBuilder()
    types = [
        ("📝 Відкрита справа", ReminderType.OPEN_TASK.value),
        ("🎂 День народження / Річниця", ReminderType.ANNIVERSARY.value),
        ("🔥 Задача з дедлайном", ReminderType.DEADLINE_TASK.value),
        ("💳 Підписка / Оренда", ReminderType.SUBSCRIPTION.value),
        ("💊 Прийом ліків", ReminderType.MEDICATION.value),
    ]
    for text, r_type in types:
        builder.button(
            text=text,
            callback_data=CreateReminderTypeCallback(reminder_type=r_type),
        )
    builder.adjust(1)
    return builder.as_markup()


def build_reminders_list_keyboard(
    page_data: PaginatedResponse[ReminderResponseDTO],
    category: str = "ALL",
) -> InlineKeyboardMarkup:
    """Генерація списку нагадувань з категорійним фільтром та пагінацією."""
    builder = InlineKeyboardBuilder()

    # Рядок кнопок фільтрації за категоріями
    filter_buttons: list[InlineKeyboardButton] = []
    for code, label in CATEGORY_FILTER_BUTTONS:
        button_text = f"• {label} •" if code == category else label
        filter_buttons.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=ReminderListFilterCallback(category=code, page=1).pack(),
            )
        )
    builder.row(*filter_buttons)

    # Список нагадувань поточної сторінки
    for rem in page_data.items:
        truncated_title = rem.title[:32]
        builder.row(
            InlineKeyboardButton(
                text=truncated_title,
                callback_data=ReminderDetailCallback(action="view", reminder_id=rem.id).pack(),
            )
        )

    # Рядок пагінації (якщо більше 1 сторінки)
    if page_data.pages > 1:
        pagination_buttons: list[InlineKeyboardButton] = []
        if page_data.page > 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Попередня",
                    callback_data=ReminderListFilterCallback(category=category, page=page_data.page - 1).pack(),
                )
            )
        if page_data.page < page_data.pages:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="Наступна ➡️",
                    callback_data=ReminderListFilterCallback(category=category, page=page_data.page + 1).pack(),
                )
            )
        if pagination_buttons:
            builder.row(*pagination_buttons)

    return builder.as_markup()


def build_reminder_detail_keyboard(reminder: ReminderResponseDTO) -> InlineKeyboardMarkup:
    """Генерація кнопок швидких дій для картки деталей конкретного нагадування."""
    builder = InlineKeyboardBuilder()

    if reminder.status in (ReminderStatus.ACTIVE, ReminderStatus.TRIAL):
        builder.row(
            InlineKeyboardButton(
                text="✅ Виконано",
                callback_data=ReminderDetailCallback(action="done", reminder_id=reminder.id).pack(),
            ),
            InlineKeyboardButton(
                text="⏸ Пауза",
                callback_data=ReminderDetailCallback(action="pause", reminder_id=reminder.id).pack(),
            ),
        )
    elif reminder.status == ReminderStatus.PAUSED:
        builder.row(
            InlineKeyboardButton(
                text="▶️ Відновити",
                callback_data=ReminderDetailCallback(action="resume", reminder_id=reminder.id).pack(),
            )
        )

    if reminder.reminder_type == ReminderType.MEDICATION:
        builder.row(
            InlineKeyboardButton(
                text="📊 Статистика прийому",
                callback_data=ReminderDetailCallback(action="stats", reminder_id=reminder.id).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🗑 Видалити",
            callback_data=ReminderDetailCallback(action="delete", reminder_id=reminder.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад до списку",
            callback_data=ReminderListFilterCallback(category="ALL", page=1).pack(),
        )
    )
    return builder.as_markup()


def build_open_task_times_keyboard() -> InlineKeyboardMarkup:
    """Швидкий вибір графіка щоденних нагадувань для відкритої справи."""
    builder = InlineKeyboardBuilder()
    options = [
        ("🕘 3 рази (09:00, 14:00, 19:00)", "09:00,14:00,19:00"),
        ("☀️ 2 рази (10:00, 18:00)", "10:00,18:00"),
        ("🌅 Вранці (09:00)", "09:00"),
    ]
    for text, value in options:
        builder.button(text=text, callback_data=CreateWizardCallback(step="open_times", value=value))
    builder.adjust(1)
    return builder.as_markup()


def build_anniversary_lead_times_keyboard() -> InlineKeyboardMarkup:
    """Швидкий вибір завчасних інтервалів нагадування для річниці чи дня народження."""
    builder = InlineKeyboardBuilder()
    options = [
        ("🔔 Стандартний (14д, 7д, 3д, 1д, 0д)", "14d,7d,3d,1d,0d"),
        ("⚡ Короткий (7д, 1д, 0д)", "7d,1d,0d"),
        ("🎯 Тільки за 1 день та в день події", "1d,0d"),
    ]
    for text, value in options:
        builder.button(text=text, callback_data=CreateWizardCallback(step="anniv_leads", value=value))
    builder.adjust(1)
    return builder.as_markup()


def build_deadline_quick_date_keyboard() -> InlineKeyboardMarkup:
    """Швидкий вибір дати дедлайну для термінових задач."""
    builder = InlineKeyboardBuilder()
    options = [
        ("Сьогодні о 18:00", "today_18"),
        ("Завтра о 12:00", "tomorrow_12"),
        ("Завтра о 18:00", "tomorrow_18"),
        ("Через 3 дні о 18:00", "in3days_18"),
    ]
    for text, value in options:
        builder.button(text=text, callback_data=CreateWizardCallback(step="dl_date", value=value))
    builder.adjust(1)
    return builder.as_markup()


def build_deadline_priority_keyboard() -> InlineKeyboardMarkup:
    """Вибір пріоритету задачі з дедлайном або автоматичної ескалації."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🤖 Автоматичний (динамична ескалація)",
        callback_data=CreateWizardCallback(step="dl_prio", value="AUTO"),
    )
    priorities = [
        ("🟢 Низький", "LOW"),
        ("🟡 Середній", "MEDIUM"),
        ("🟠 Високий", "HIGH"),
        ("🔴 Критичний", "CRITICAL"),
    ]
    for text, value in priorities:
        builder.button(text=text, callback_data=CreateWizardCallback(step="dl_prio", value=value))
    builder.adjust(1, 2, 2)
    return builder.as_markup()


def build_subscription_billing_keyboard() -> InlineKeyboardMarkup:
    """Швидкий вибір дати та періодичності платіжного циклу підписки."""
    builder = InlineKeyboardBuilder()
    options = [
        ("📅 Сьогоднішнє число (щомісяця)", "today_1"),
        ("1️⃣ 1-ше число щомісяця", "1_1"),
        ("🔟 15-те число щомісяця", "15_1"),
        ("📆 Сьогоднішнє число (щорічно)", "today_12"),
    ]
    for text, value in options:
        builder.button(text=text, callback_data=CreateWizardCallback(step="sub_bill", value=value))
    builder.adjust(1)
    return builder.as_markup()


def build_subscription_mode_keyboard() -> InlineKeyboardMarkup:
    """Вибір режиму підписки: звичайна, пробний період (Trial) або знижка."""
    builder = InlineKeyboardBuilder()
    options = [
        ("✅ Звичайна платна підписка", "regular"),
        ("🎁 Безкоштовний Trial-період", "trial"),
        ("🏷 Акційна знижка на перші N циклів", "discount"),
    ]
    for text, value in options:
        builder.button(text=text, callback_data=CreateWizardCallback(step="sub_mode", value=value))
    builder.adjust(1)
    return builder.as_markup()


def build_medication_schedule_mode_keyboard() -> InlineKeyboardMarkup:
    """Вибір типу графіку прийому лікарського засобу."""
    builder = InlineKeyboardBuilder()
    options = [
        ("⏰ Щодня у фіксовані години", "daily"),
        ("🔄 Кожні N годин", "interval"),
    ]
    for text, value in options:
        builder.button(text=text, callback_data=CreateWizardCallback(step="med_mode", value=value))
    builder.adjust(1)
    return builder.as_markup()


def build_medication_duration_keyboard() -> InlineKeyboardMarkup:
    """Швидкий вибір тривалості курсу прийому медикаментів."""
    builder = InlineKeyboardBuilder()
    durations = [
        ("5 днів", "5"),
        ("7 днів", "7"),
        ("10 днів", "10"),
        ("14 днів", "14"),
        ("30 днів", "30"),
        ("♾ Безстроково", "0"),
    ]
    for text, value in durations:
        builder.button(text=text, callback_data=CreateWizardCallback(step="med_dur", value=value))
    builder.adjust(3, 3)
    return builder.as_markup()


def build_medication_strict_keyboard() -> InlineKeyboardMarkup:
    """Налаштування поведінки прийому ліків у нічні тихі години."""
    builder = InlineKeyboardBuilder()
    options = [
        ("🌙 Без звуку вночі (тихий режим)", "false"),
        ("🚨 Суворий графік — зі звуком навіть уночі!", "true"),
    ]
    for text, value in options:
        builder.button(text=text, callback_data=CreateWizardCallback(step="med_strict", value=value))
    builder.adjust(1)
    return builder.as_markup()
