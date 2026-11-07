import html
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.api.schemas.pagination import PaginatedResponse
from src.infrastructure.notifications.dto import (
    NotificationEventType,
    NotificationPayload,
)
from src.modules.finance.queries.dto import ExchangeRateResponseDTO
from src.modules.reminders.domain.enums import (
    MedicationLogStatus,
    Priority,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.queries.dto import (
    MedicationAdherenceStatsDTO,
    ReminderResponseDTO,
)
from src.modules.users.queries.dto import (
    UserResponseDTO,
    UserSettingsResponseDTO,
)

_BANK_LABELS: dict[str, str] = {
    "NBU": "НБУ (Національний банк України)",
    "MONOBANK": "Monobank (Монобанк)",
    "PRIVATBANK": "ПриватБанк",
}

_TYPE_ICONS: dict[ReminderType, str] = {
    ReminderType.ANNIVERSARY: "🎂",
    ReminderType.OPEN_TASK: "📝",
    ReminderType.DEADLINE_TASK: "🔥",
    ReminderType.SUBSCRIPTION: "💳",
    ReminderType.MEDICATION: "💊",
}

_TYPE_NAMES: dict[ReminderType, str] = {
    ReminderType.ANNIVERSARY: "Річниця / День народження",
    ReminderType.OPEN_TASK: "Відкрита справа",
    ReminderType.DEADLINE_TASK: "Задача з дедлайном",
    ReminderType.SUBSCRIPTION: "Підписка / Оренда",
    ReminderType.MEDICATION: "Прийом ліків",
}

_STATUS_LABELS: dict[ReminderStatus, str] = {
    ReminderStatus.ACTIVE: "🟢 Активне",
    ReminderStatus.PAUSED: "⏸ Призупинено",
    ReminderStatus.COMPLETED: "✅ Виконано",
    ReminderStatus.CANCELLED: "❌ Скасовано",
    ReminderStatus.TRIAL: "🎁 Пробний період",
}

_PRIORITY_LABELS: dict[Priority, str] = {
    Priority.LOW: "🟢 Низький",
    Priority.MEDIUM: "🟡 Середній",
    Priority.HIGH: "🟠 Високий",
    Priority.CRITICAL: "🔴 Критичний",
}

_NOTIFICATION_PRIORITY_BADGES: dict[str, str] = {
    Priority.LOW: "[НИЗЬКИЙ]",
    Priority.MEDIUM: "[СЕРЕДНІЙ]",
    Priority.HIGH: "[ВИСОКИЙ]",
    Priority.CRITICAL: "[КРИТИЧНО]",
}

_SCHEDULE_LOGIC_NAMES: dict[ScheduleLogicType, str] = {
    ScheduleLogicType.DAILY_AT_TIMES: "Щоденно в обрані години",
    ScheduleLogicType.INTERVAL_HOURS: "Інтервал кожні N годин",
    ScheduleLogicType.INTERVAL_DAYS: "Інтервал кожні N днів",
    ScheduleLogicType.EXACT_DATETIME_DEADLINE: "Точний дедлайн з ескалацією (дата і час)",
    ScheduleLogicType.EXACT_DATE_DEADLINE: "Точний дедлайн (дата)",
    ScheduleLogicType.DATE_WITH_MONTH_INTERVAL: "Дата з місячним або річним інтервалом",
}

_MED_STATUS_LABELS: dict[MedicationLogStatus, str] = {
    MedicationLogStatus.TAKEN: "✅ Прийнято",
    MedicationLogStatus.MISSED: "❌ Пропущено",
    MedicationLogStatus.SNOOZED: "⏰ Відкладено",
}


def _format_local_datetime(
    dt: datetime,
    user_timezone: str,
    date_format: str = "%d.%m.%Y %H:%M",
) -> str:
    """Конвертує UTC datetime у часовий пояс користувача та повертає форматований рядок."""
    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))

    local_dt = dt.astimezone(tz)
    return local_dt.strftime(date_format)


def format_welcome_message(user: UserResponseDTO) -> str:
    """Генерує вітальне HTML-повідомлення для користувача Telegram."""
    display_name = user.username
    if user.telegram_account and user.telegram_account.tg_full_name:
        display_name = user.telegram_account.tg_full_name

    safe_name = html.escape(display_name)
    return (
        f"👋 <b>Вітаємо у Reminder App, {safe_name}!</b>\n\n"
        "Я ваш розумний персональний асистент для надійного керування всіма нагадуваннями, "
        "регулярними платежами, дедлайнами та курсами ліків.\n\n"
        "<b>Основні можливості:</b>\n"
        "• 🎂 <b>Річниці та дні народження:</b> каскад завчасних нагадувань (за 14, 7, 3, 1 день та в день події).\n"
        "• 📝 <b>Відкриті справи:</b> щоденні повтори (вранці, вдень, ввечері) до завершення завдання.\n"
        "• 🔥 <b>Задачі з дедлайнами:</b> розумна динамічна ескалація пріоритету при наближенні дедлайну.\n"
        "• 💳 <b>Підписки та оренда:</b> автоконвертація валют за картковим курсом, контроль тріалів і знижок.\n"
        "• 💊 <b>Курси ліків:</b> періодичні прийоми, нічний режим та повний журнал комплаєнсу.\n\n"
        "<i>Оберіть потрібну дію в меню нижче або натисніть /help для детальної довідки.</i>"
    )


def format_help_message() -> str:
    """Генерує детальну довідку щодо команд та можливостей бота."""
    return (
        "<b>📖 Довідка щодо роботи з Reminder Bot</b>\n\n"
        "<b>Основні команди бота:</b>\n"
        "/start — Перезапуск головного меню та синхронізація профілю\n"
        "/new — Запустити майстер створення нового нагадування\n"
        "/list — Перегляд списку нагадувань з фільтрами та пагінацією\n"
        "/rates — Свіжі банківські курси валют (НБУ, Monobank, ПриватБанк)\n"
        "/settings — Налаштування (часовий пояс, тихі години, пріоритетний банк)\n"
        "/cancel — Скасування поточної форми або діалогу створення\n"
        "/help — Ця довідка\n\n"
        "<b>5 підтримуваних типів нагадувань:</b>\n"
        "1. 🎂 <b>Річниця:</b> пам'ятні дати з підрахунком років та каскадом сповіщень.\n"
        "2. 📝 <b>Відкрита справа:</b> регулярні справи без дедлайну (1–3 рази на день).\n"
        "3. 🔥 <b>Дедлайн:</b> задача з фіксованим часом завершення. Пріоритет зростає автоматично!\n"
        "4. 💳 <b>Підписка:</b> регулярні платежі (USD/EUR конвертуються за курсом обраного банку).\n"
        "5. 💊 <b>Ліки:</b> графік прийому медикаментів з фіксацією результатів у журналі."
    )


def format_settings_message(settings: UserSettingsResponseDTO) -> str:
    """Форматує картку користувацьких налаштувань."""
    bank_code = (
        settings.preferred_bank.value if hasattr(settings.preferred_bank, "value") else str(settings.preferred_bank)
    )
    bank_title = _BANK_LABELS.get(bank_code, bank_code)
    escalate_badge = "Увімкнено ✅" if settings.auto_deadline_priority_escalation else "Вимкнено ❌"
    quiet_start = settings.quiet_hours_start.strftime("%H:%M")
    quiet_end = settings.quiet_hours_end.strftime("%H:%M")

    return (
        "<b>⚙️ Ваші налаштування</b>\n\n"
        f"🌍 <b>Часовий пояс:</b> <code>{html.escape(settings.timezone)}</code>\n"
        f"🌙 <b>Тихі години:</b> <code>{quiet_start} – {quiet_end}</code>\n"
        f"🏦 <b>Пріоритетний банк:</b> <b>{html.escape(bank_title)}</b>\n"
        f"📈 <b>Автоескалація дедлайнів:</b> {escalate_badge}\n"
        f"🔢 <b>Версія даних (OCC):</b> <code>v{settings.version}</code>\n\n"
        "<i>Натисніть кнопку нижче, щоб швидко змінити обраний параметр:</i>"
    )


def format_rates_message(rates: list[ExchangeRateResponseDTO], preferred_bank: str) -> str:
    """Форматує зведення останніх курсів валют НБУ, Monobank та ПриватБанку."""
    if not rates:
        return "<b>💱 Актуальні курси валют</b>\n\n<i>Дані щодо курсів валют тимчасово недоступні.</i>"

    by_provider: dict[str, list[ExchangeRateResponseDTO]] = {}
    for r in rates:
        p_val = r.provider.value if hasattr(r.provider, "value") else str(r.provider)
        by_provider.setdefault(p_val, []).append(r)

    bank_names = {
        "NBU": "НБУ (Національний банк України)",
        "MONOBANK": "Monobank",
        "PRIVATBANK": "ПриватБанк",
    }

    lines = ["<b>💱 Актуальні курси валют до гривні (UAH)</b>\n"]
    pref_label = bank_names.get(preferred_bank, preferred_bank)
    lines.append(f"⭐ <i>Ваш пріоритетний банк: <b>{html.escape(pref_label)}</b></i>\n")

    for p_code, p_rates in by_provider.items():
        title = bank_names.get(p_code, p_code)
        is_fav = p_code == preferred_bank
        star = " ⭐ (Пріоритетний)" if is_fav else ""
        lines.append(f"<b>🏦 {html.escape(title)}{star}</b>")

        for r in p_rates:
            flag = "💵" if r.target_currency == "USD" else ("💶" if r.target_currency == "EUR" else "🪙")
            if r.rate_buy is not None and r.rate_buy > 0:
                lines.append(
                    f"  {flag} <b>{html.escape(r.target_currency)}:</b> "
                    f"купівля <code>{r.rate_buy:.2f}</code> | продаж <code>{r.rate_sell:.2f}</code> грн"
                )
            else:
                lines.append(
                    f"  {flag} <b>{html.escape(r.target_currency)}:</b> "
                    f"офіційний курс <code>{r.rate_sell:.2f}</code> грн"
                )
        lines.append("")

    return "\n".join(lines).strip()


def format_reminders_list_message(
    page_data: PaginatedResponse[ReminderResponseDTO],
    category: str,
    user_timezone: str,
) -> str:
    """Форматує сторінку пагінованого списку нагадувань користувача."""
    category_labels = {
        "ALL": "Усі категорії",
        "ANNIVERSARY": "🎂 Річниці",
        "OPEN_TASK": "📝 Відкриті справи",
        "DEADLINE_TASK": "🔥 Дедлайни",
        "SUBSCRIPTION": "💳 Підписки",
        "MEDICATION": "💊 Ліки",
    }
    cat_title = category_labels.get(category, category)

    if not page_data.items:
        return (
            f"<b>📋 Список нагадувань ({html.escape(cat_title)})</b>\n\n"
            "<i>У цій категорії наразі немає створених нагадувань.</i>\n\n"
            "Щоб створити нове нагадування, натисніть кнопку <b>➕ Створити нагадування</b>."
        )

    lines = [f"<b>📋 Ваші нагадування ({html.escape(cat_title)})</b>\n"]

    for idx, rem in enumerate(page_data.items, start=1):
        icon = _TYPE_ICONS.get(rem.reminder_type, "📌")
        status_label = _STATUS_LABELS.get(rem.status, str(rem.status.value))
        safe_title = html.escape(rem.title)
        next_trigger_str = _format_local_datetime(rem.next_trigger_at, user_timezone)

        lines.append(f"<b>{idx}.</b> {icon} <b>{safe_title}</b> [{status_label}]")
        lines.append(f"   ⏰ Наступне: <code>{next_trigger_str}</code>")

        if rem.regular_amount is not None and rem.currency:
            lines.append(f"   💰 Сума: <code>{rem.regular_amount:.2f} {rem.currency}</code>")
        if rem.due_datetime is not None:
            due_str = _format_local_datetime(rem.due_datetime, user_timezone)
            lines.append(f"   🚨 Дедлайн: <code>{due_str}</code>")

        lines.append("")

    total_pages = max(1, page_data.pages)
    lines.append(f"<i>Сторінка {page_data.page} з {total_pages} (Всього: {page_data.total} записів)</i>")
    return "\n".join(lines).strip()


def format_reminder_detail_message(
    reminder: ReminderResponseDTO,
    user_timezone: str,
) -> str:
    """Форматує повну інформаційну картку нагадування для перегляду деталей."""
    icon = _TYPE_ICONS.get(reminder.reminder_type, "📌")
    type_name = _TYPE_NAMES.get(reminder.reminder_type, str(reminder.reminder_type.value))
    status_label = _STATUS_LABELS.get(reminder.status, str(reminder.status.value))
    logic_name = _SCHEDULE_LOGIC_NAMES.get(
        reminder.schedule_logic,
        str(reminder.schedule_logic.value),
    )
    safe_title = html.escape(reminder.title)
    next_trigger_str = _format_local_datetime(reminder.next_trigger_at, user_timezone)
    created_at_str = _format_local_datetime(reminder.created_at, user_timezone)

    lines = [
        f"{icon} <b>{safe_title}</b>\n",
        f"📌 <b>Тип:</b> {type_name}",
        f"📊 <b>Статус:</b> {status_label}",
        f"⏰ <b>Наступне спрацювання:</b> <code>{next_trigger_str}</code>",
        f"🔄 <b>Логіка графіку:</b> {logic_name}",
    ]

    if reminder.description:
        lines.append(f"📝 <b>Опис:</b> {html.escape(reminder.description)}")

    # Специфічні поля для задач з дедлайном
    if reminder.due_datetime:
        due_str = _format_local_datetime(reminder.due_datetime, user_timezone)
        prio = reminder.calculated_priority or reminder.base_priority
        prio_label = _PRIORITY_LABELS.get(prio, "Звичайний") if prio else "Автоматичний"
        lines.append(f"🚨 <b>Крайній термін (дедлайн):</b> <code>{due_str}</code>")
        lines.append(f"🎯 <b>Пріоритет:</b> {prio_label}")

    # Специфічні поля для підписок
    if reminder.regular_amount is not None and reminder.currency:
        lines.append(f"💳 <b>Регулярна вартість:</b> <code>{reminder.regular_amount:.2f} {reminder.currency}</code>")
        if reminder.is_trial:
            trial_end_str = reminder.trial_end_date.strftime("%d.%m.%Y") if reminder.trial_end_date else "не вказано"
            lines.append(f"🎁 <b>Пробний період:</b> триває до <code>{trial_end_str}</code>")
        elif (
            reminder.discount_amount is not None
            and reminder.discount_cycles_remaining is not None
            and reminder.discount_cycles_remaining > 0
        ):
            lines.append(
                f"🏷 <b>Акційна вартість:</b> <code>{reminder.discount_amount:.2f} {reminder.currency}</code> "
                f"(залишилось {reminder.discount_cycles_remaining} з {reminder.discount_cycles_total or 0} циклів)"
            )

    # Специфічні поля для ліків
    if reminder.course_duration_days is not None:
        lines.append(f"💊 <b>Тривалість курсу:</b> {reminder.course_duration_days} днів")
        if reminder.medication_start_date:
            lines.append(f"📅 <b>Початок курсу:</b> {reminder.medication_start_date.strftime('%d.%m.%Y')}")
        if reminder.medication_end_date:
            lines.append(f"🏁 <b>Завершення курсу:</b> {reminder.medication_end_date.strftime('%d.%m.%Y')}")
        strict_text = (
            "🚨 Суворий (будити навіть уночі)" if reminder.strict_schedule else "🌙 М'який (переносити на ранок)"
        )
        lines.append(f"🛡 <b>Нічний режим:</b> {strict_text}")

    # Завчасні нагадування
    if reminder.lead_times:
        lines.append(f"🔔 <b>Завчасні сповіщення:</b> {', '.join(reminder.lead_times)}")

    lines.append("")
    lines.append(
        f"<i>Створено: {created_at_str} | Версія OCC: v{reminder.version} | ID: <code>{reminder.id}</code></i>"
    )
    return "\n".join(lines).strip()


def format_medication_stats_message(
    reminder: ReminderResponseDTO,
    stats: MedicationAdherenceStatsDTO,
    user_timezone: str,
) -> str:
    """Форматує статистику дотримання курсу лікування (комплаєнсу) пацієнта."""
    safe_title = html.escape(reminder.title)
    lines = [
        f"<b>📊 Статистика прийому ліків: {safe_title}</b>\n",
        f"📈 <b>Рівень комплаєнсу:</b> <b>{stats.adherence_rate_percent:.1f}%</b>",
        f"📋 <b>Усього запланованих прийомів:</b> {stats.total_logs}",
        f"✅ <b>Успішно прийнято:</b> {stats.taken_count}",
        f"⏰ <b>Відкладено прийом:</b> {stats.snoozed_count}",
        f"❌ <b>Пропущено:</b> {stats.missed_count}\n",
        "<b>Історія останніх відміток:</b>",
    ]

    if not stats.logs:
        lines.append("<i>Журнал прийомів наразі порожній.</i>")
    else:
        for log in stats.logs[:10]:
            status_text = _MED_STATUS_LABELS.get(log.status, str(log.status.value))
            sched_time = _format_local_datetime(log.scheduled_at, user_timezone)
            actual_time = (
                f" (факт: {_format_local_datetime(log.recorded_at, user_timezone, '%H:%M')})" if log.recorded_at else ""
            )
            lines.append(f"• <code>{sched_time}</code> — {status_text}{actual_time}")

    return "\n".join(lines).strip()


def format_action_confirmation(
    original_text: str,
    action: str,
    updated: ReminderResponseDTO,
    minutes: int,
    user_timezone: str,
) -> str:
    """
    Генерує підтвердження виконання дії над нагадуванням для оновлення тексту повідомлення.

    Перекреслює попередній текст та додає статус результату дії українською мовою.
    """
    next_trigger_str = _format_local_datetime(updated.next_trigger_at, user_timezone)

    if action == "payment":
        prefix = f"✅ <b>Оплату підписки зафіксовано!</b>\nНаступне списання: <code>{next_trigger_str}</code>"
    elif action == "med_taken":
        prefix = f"✅ <b>Прийом ліків зафіксовано!</b>\nНаступний прийом: <code>{next_trigger_str}</code>"
    elif action == "med_missed":
        prefix = f"⏭ <b>Прийом ліків позначено як пропущений.</b>\nНаступний прийом: <code>{next_trigger_str}</code>"
    elif action == "complete":
        prefix = "✅ <b>Нагадування позначено як виконане!</b>"
    elif action == "cancel":
        prefix = "❌ <b>Підписку успішно скасовано.</b>"
    elif action == "snooze":
        prefix = f"⏰ <b>Відкладено на {minutes} хв</b> (до <code>{next_trigger_str}</code>)."
    elif action == "pause":
        prefix = "⏸ <b>Нагадування переведено на паузу.</b>"
    elif action == "resume":
        prefix = f"▶️ <b>Нагадування відновлено!</b>\nНаступне спрацювання: <code>{next_trigger_str}</code>"
    elif action == "delete":
        prefix = "🗑 <b>Нагадування успішно видалено.</b>"
    else:
        prefix = f"✅ <b>Дію '{html.escape(action)}' успішно виконано!</b>"

    cleaned_original = html.escape(original_text.strip()) if original_text else ""
    if cleaned_original:
        return f"{prefix}\n\n<s>{cleaned_original}</s>"
    return prefix


def format_notification_payload(payload: NotificationPayload) -> str:
    """
    Генерує фінальне HTML-повідомлення сповіщення для відправки в Telegram.

    Підтримує рендеринг щоденного дайджесту, сповіщень про закінчення пробного періоду
    та планових спрацювань усіх 5 типів нагадувань з екрануванням спецсимволів HTML.
    """
    # 1. Щоденний дайджест відкритих справ
    if payload.event_type == NotificationEventType.DAILY_DIGEST:
        header = "📋 <b>Ваш щоденний дайджест відкритих справ:</b>\n\n"
        if not payload.digest_tasks:
            return header + "<i>На сьогодні немає відкритих справ.</i>"

        bullet_lines: list[str] = []
        for task in payload.digest_tasks:
            safe_task_title = html.escape(task.title)
            prio_badge = ""
            if task.priority is not None:
                badge = _NOTIFICATION_PRIORITY_BADGES.get(task.priority, "")
                if badge:
                    prio_badge = f"{badge} "
            line = f"• {prio_badge}<b>{safe_task_title}</b>"
            if task.description:
                line += f"\n  {html.escape(task.description)}"
            bullet_lines.append(line)

        return header + "\n".join(bullet_lines)

    safe_title = html.escape(payload.title) if payload.title else ""

    # 2. Завершення пробного періоду підписки
    if payload.event_type == NotificationEventType.TRIAL_EXPIRED:
        amount = payload.amount if payload.amount is not None else Decimal("0.00")
        currency = str(payload.currency) if payload.currency is not None else "UAH"
        return (
            f"💳 <b>Пробний період підписки «{safe_title}» завершився!</b>\n"
            "Підписку переведено у регулярний платний статус.\n"
            f"Сума чергового списання: <code>{amount:.2f} {currency}</code>."
        )

    # 3. Планове спрацювання нагадування (REMINDER_DUE)
    if payload.event_type == NotificationEventType.REMINDER_DUE:
        if payload.reminder_type == ReminderType.SUBSCRIPTION:
            amount = payload.amount if payload.amount is not None else Decimal("0.00")
            currency = str(payload.currency) if payload.currency is not None else "UAH"
            text = (
                f"💳 <b>Нагадування про оплату підписки: {safe_title}</b>\n"
                f"Сума до сплати: <code>{amount:.2f} {currency}</code>"
            )
            if payload.converted_amount_uah is not None and payload.rate_provider:
                safe_provider = html.escape(payload.rate_provider)
                text += f" (≈ <b>{payload.converted_amount_uah:.2f} грн</b> за курсом {safe_provider})"
            if payload.is_stale_rate_fallback:
                text += "\n⚠️ <i>Курс обраного банку застарілий, використано офіційний курс НБУ.</i>"
            if payload.is_trial:
                text += "\n⚠️ <b>Закінчується пробний період підписки!</b>"
            elif payload.is_last_discount_cycle:
                text += "\n⚠️ <b>Це останній платіжний цикл за зниженою акційною ціною!</b>"
            if payload.description:
                text += f"\n{html.escape(payload.description)}"
            return text

        if payload.reminder_type == ReminderType.MEDICATION:
            text = f"💊 <b>Час прийому ліків: {safe_title}</b>"
            if payload.description:
                text += f"\n{html.escape(payload.description)}"
            if payload.medication_end_date:
                text += f"\nКурс триває до: <code>{payload.medication_end_date.strftime('%d.%m.%Y')}</code>"
            return text

        if payload.reminder_type == ReminderType.DEADLINE_TASK:
            prio_badge = (
                _NOTIFICATION_PRIORITY_BADGES.get(payload.effective_priority, "[ЗВИЧАЙНИЙ]")
                if payload.effective_priority
                else "[ЗВИЧАЙНИЙ]"
            )
            text = f"🔥 <b>{prio_badge} Дедлайн задачі: {safe_title}</b>"
            if payload.due_datetime:
                due_formatted = _format_local_datetime(payload.due_datetime, payload.user_timezone)
                text += f"\nТермін виконання: <code>{due_formatted}</code>"
            if payload.description:
                text += f"\n{html.escape(payload.description)}"
            return text

        if payload.reminder_type == ReminderType.ANNIVERSARY:
            age_text = f" ({payload.calculated_age} р.)" if payload.calculated_age is not None else ""
            text = f"🎉 <b>Сьогодні святкова подія: {safe_title}{age_text}!</b>"
            if payload.description:
                text += f"\n{html.escape(payload.description)}"
            return text

        if payload.reminder_type == ReminderType.OPEN_TASK:
            text = f"📋 <b>Нагадування про справу: {safe_title}</b>"
            if payload.description:
                text += f"\n{html.escape(payload.description)}"
            return text

    # Запасний варіант для невідомих подій або типів
    fallback_text = f"🔔 <b>{safe_title}</b>"
    if payload.description:
        fallback_text += f"\n{html.escape(payload.description)}"
    return fallback_text
