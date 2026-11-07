from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm.base import NO_VALUE


def is_loaded(model_instance: Any, relationship_name: str) -> bool:
    """
    Безпечно перевіряє, чи завантажений зв'язок або атрибут ORM-моделі без виклику lazy='raise'.

    Повертає True, якщо атрибут завантажений у пам'ять або об'єкт не інспектується SQLAlchemy,
    та False, якщо доступ до нього викличе помилку неявного I/O запиту.
    """
    insp = inspect(model_instance, raiseerr=False)
    if insp is None:
        return hasattr(model_instance, relationship_name)
    attr = insp.attrs.get(relationship_name)
    return bool(attr is not None and attr.loaded_value is not NO_VALUE)


def get_loaded[T](model_instance: Any, relationship_name: str, default: T | None = None) -> Any | T:
    """
    Безпечно повертає завантажений зв'язок або атрибут ORM-моделі без спрацювання lazy='raise'.

    Якщо зв'язок не був попередньо завантажений через Eager Loading (selectinload/joinedload),
    повертає передане значення за замовчуванням (default).
    """
    insp = inspect(model_instance, raiseerr=False)
    if insp is None:
        return getattr(model_instance, relationship_name, default)
    attr = insp.attrs.get(relationship_name)
    if attr is None or attr.loaded_value is NO_VALUE:
        return default
    return attr.loaded_value
