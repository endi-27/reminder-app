from enum import Enum
from typing import Any


def unwrap_enum(value: Any) -> str:
    """
    Уніфіковане вилучення рядкового значення з Enum або рядка.
    Якщо передано Enum — повертає value.value (перетворене на str), інакше str(value).
    """
    return str(value.value) if isinstance(value, Enum) else str(value)


def unwrap_enum_or_none(value: Any) -> str | None:
    """
    Уніфіковане вилучення рядкового значення з опціонального Enum або рядка.
    Якщо передано None — повертає None.
    """
    if value is None:
        return None
    return str(value.value) if isinstance(value, Enum) else str(value)
