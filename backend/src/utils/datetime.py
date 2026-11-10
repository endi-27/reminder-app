import zoneinfo
from datetime import UTC, datetime

# Відключаємо пошук у системних каталогах ОС (/usr/share/zoneinfo тощо),
# змушуючи стандартний модуль zoneinfo використовувати виключно офіційний пакет tzdata (IANA)
zoneinfo.reset_tzpath(to=())


def configure_tzdata() -> None:
    """
    Налаштовує стандартний модуль zoneinfo на використання виключно
    пакета tzdata (IANA Time Zone Database) замість системних файлів ОС.
    """
    zoneinfo.reset_tzpath(to=())


def get_timezone(timezone_name: str) -> zoneinfo.ZoneInfo:
    """
    Повертає об'єкт ZoneInfo для вказаної назви часового поясу IANA,
    гарантовано завантажений із пакета tzdata.
    """
    return zoneinfo.ZoneInfo(timezone_name)


def is_valid_timezone(timezone_name: str) -> bool:
    """
    Перевіряє валідність назви часового поясу IANA за допомогою пакета tzdata.
    """
    if not timezone_name or not isinstance(timezone_name, str):
        return False
    try:
        zoneinfo.ZoneInfo(timezone_name)
        return True
    except Exception:
        return False


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
