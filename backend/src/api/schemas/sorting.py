import enum
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Select, asc, desc


class SortOrder(enum.StrEnum):
    """Напрямок сортування результатів вибірки."""

    ASC = "asc"
    DESC = "desc"


def apply_sorting(
    stmt: Select[Any],
    sort_by: str,
    sort_order: SortOrder,
    allowed_columns: Mapping[str, Any],
    default_column: Any,
) -> Select[Any]:
    """
    Застосовує сортування до SQL-запиту за дозволеним списком колонок.

    Якщо зазначена колонка sort_by відсутня серед allowed_columns,
    застосовується сортування за default_column.
    """
    col = allowed_columns.get(sort_by, default_column)
    order_clause = desc(col) if sort_order == SortOrder.DESC else asc(col)
    return stmt.order_by(order_clause)
