from datetime import UTC, datetime


def now_utc() -> datetime:
    """Повертає поточний системний час у часовому поясі UTC."""
    return datetime.now(UTC)


def ensure_utc_datetime(dt: datetime) -> datetime:
    """
    Гарантує, що об'єкт datetime є timezone-aware та наведений до часового поясу UTC.

    Примітка: для naive datetime об'єктів (де tzinfo is None) функція припускає, що мітка
    вже представляє UTC-час, і призначає часовий пояс UTC без зсуву годин.
    Для timezone-aware об'єктів виконується коректна конвертація до UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
