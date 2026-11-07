import math
from collections.abc import Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class PaginationParams(BaseModel):
    """Стандартні параметри пагінації для Read-запитів."""

    model_config = ConfigDict(extra="forbid")

    page: Annotated[int, Field(default=1, ge=1, description="Номер сторінки (починаючи з 1)")] = 1
    size: Annotated[
        int,
        Field(default=20, ge=1, le=100, description="Кількість елементів на сторінці (макс. 100)"),
    ] = 20

    @property
    def offset(self) -> int:
        """Зміщення записів для SQL LIMIT/OFFSET."""
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        """Кількість записів для SQL LIMIT."""
        return self.size


class PaginatedResponse[T](BaseModel):
    """Уніфікована схема пагінованої відповіді для Read-ендпоінтів."""

    items: Annotated[list[T], Field(description="Список елементів поточної сторінки")]
    total: Annotated[int, Field(ge=0, description="Загальна кількість записів за фільтром")]
    page: Annotated[int, Field(ge=1, description="Поточна сторінка")]
    size: Annotated[int, Field(ge=1, description="Розмір сторінки")]
    pages: Annotated[int, Field(ge=0, description="Загальна кількість сторінок")]

    @classmethod
    def create(
        cls,
        items: Sequence[T],
        total: int,
        params: PaginationParams,
    ) -> "PaginatedResponse[T]":
        """Фабричний метод створення пагінованої відповіді з автоматичним розрахунком сторінок."""
        pages = math.ceil(total / params.size) if total > 0 else 0
        return cls(
            items=list(items),
            total=total,
            page=params.page,
            size=params.size,
            pages=pages,
        )
