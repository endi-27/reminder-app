import abc
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


def escape_like(value: str) -> str:
    """Екранування спецсимволів SQL LIKE (%, _, \\) для безпечного пошуку підрядка."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class BaseQueryService(abc.ABC):  # noqa: B024
    """Базовий клас для Read-Side CQRS сервісів вибірок."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _escape_like(value: str) -> str:
        """Екранування спецсимволів SQL LIKE (%, _, \\) для безпечного пошуку підрядка."""
        return escape_like(value)

    @staticmethod
    def _apply_date_range(
        stmt: Select[Any],
        column: Any,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
    ) -> Select[Any]:
        """
        Уніфіковане застосування фільтра діапазону дат або часових міток.

        Підтримує:
        1. datetime (UTC) — точне включне порівняння column >= date_from та column <= date_to.
        2. date — напіввідкритий інтервал [date_from 00:00:00, date_to + 1 день 00:00:00)
           для повного охоплення кінцевого дня.
        """
        if date_from is not None:
            if isinstance(date_from, datetime):
                dt_from = date_from if date_from.tzinfo is not None else date_from.replace(tzinfo=UTC)
                stmt = stmt.where(column >= dt_from)
            elif isinstance(date_from, date):
                dt_from = datetime.combine(date_from, time.min, tzinfo=UTC)
                stmt = stmt.where(column >= dt_from)

        if date_to is not None:
            if isinstance(date_to, datetime):
                dt_to = date_to if date_to.tzinfo is not None else date_to.replace(tzinfo=UTC)
                stmt = stmt.where(column <= dt_to)
            elif isinstance(date_to, date):
                next_day = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
                stmt = stmt.where(column < next_day)

        return stmt

    async def _count_total(self, stmt: Select[Any]) -> int:
        """
        Оптимізований підрахунок загальної кількості рядків для пагінації.

        Знімає сортування ORDER BY через підзапит для підвищення швидкодії у PostgreSQL.
        """
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        return (await self._session.execute(count_stmt)).scalar_one()
