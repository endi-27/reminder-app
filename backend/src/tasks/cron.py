from arq.cron import cron

from src.tasks.functions import (
    cron_check_due_reminders,
    cron_check_expiring_trials_and_discounts,
    cron_daily_task_digest,
    cron_sync_exchange_rates,
)

# Розклад періодичних cron-задач фонового планувальника ARQ (docs/ARCHITECTURE.md, розділ 6)
CRON_JOBS = [
    # 1. Щохвилинна перевірка та відправка чергових нагадувань на 00-й секунді
    cron(
        cron_check_due_reminders,
        second=0,
        unique=True,
    ),
    # 2. Синхронізація банківських курсів валют кожні 6 годин (та при старті воркера)
    cron(
        cron_sync_exchange_rates,
        hour={0, 6, 12, 18},
        minute=5,
        second=0,
        run_at_startup=True,
        unique=True,
    ),
    # 3. Перевірка відкритих задач для щоденного дайджесту (кожні 30 хвилин)
    cron(
        cron_daily_task_digest,
        minute={0, 30},
        second=15,
        unique=True,
    ),
    # 4. Щоденна перевірка закінчення пробних періодів та знижок о 07:00:30 UTC
    cron(
        cron_check_expiring_trials_and_discounts,
        hour=7,
        minute=0,
        second=30,
        unique=True,
    ),
]
