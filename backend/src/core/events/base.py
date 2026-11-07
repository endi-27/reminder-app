import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field
from uuid6 import uuid7

from src.core.context import get_correlation_id, get_current_user_id


def _to_snake_case(name: str) -> str:
    """Конвертує PascalCase назву класу в UPPER_SNAKE_CASE (напр. UserCreatedEvent -> USER_CREATED)."""
    if name.endswith("Event"):
        name = name[:-5]
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
    return s


class BaseEvent(BaseModel):
    """
    Базовий незмінний клас доменних та системних подій.
    Усі атрибути події є незмінними після створення (frozen=True).
    """

    model_config = ConfigDict(frozen=True)

    if TYPE_CHECKING:
        # Для коректної генерації необов'язкових параметрів у конструкторі плагіном pydantic.mypy
        event_id: Annotated[UUID, Field(default_factory=uuid7)] = None  # type: ignore[assignment]
        timestamp: Annotated[datetime, Field(default_factory=lambda: datetime.now(UTC))] = None  # type: ignore[assignment]
        entity_id: Annotated[UUID | None, Field(default=None)] = None
        actor_id: Annotated[UUID | None, Field(default_factory=get_current_user_id)] = None
        correlation_id: Annotated[str | None, Field(default_factory=get_correlation_id)] = None
        event_name_override: Annotated[str | None, Field(default=None)] = None
    else:
        event_id: Annotated[
            UUID,
            Field(
                default_factory=uuid7,
                description="Унікальний часово-впорядкований ID події (UUIDv7)",
            ),
        ]
        timestamp: Annotated[
            datetime,
            Field(
                default_factory=lambda: datetime.now(UTC),
                description="UTC мітка часу події",
            ),
        ]
        entity_id: Annotated[
            UUID | None,
            Field(
                default=None,
                description="ID цільової сутності (якщо застосовно)",
            ),
        ] = None
        actor_id: Annotated[
            UUID | None,
            Field(
                default_factory=get_current_user_id,
                description="ID користувача, що ініціював дію (для аудит-логу)",
            ),
        ]
        correlation_id: Annotated[
            str | None,
            Field(
                default_factory=get_correlation_id,
                description="Request ID для наскрізного трасування",
            ),
        ]
        event_name_override: Annotated[
            str | None,
            Field(
                default=None,
                description="Опціональне явне перевизначення назви події",
            ),
        ] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def event_name(self) -> str:
        """Повертає назву події (явну або згенеровану з назви класу в UPPER_SNAKE_CASE)."""
        if self.event_name_override:
            return self.event_name_override
        return _to_snake_case(self.__class__.__name__)
