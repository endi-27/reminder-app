from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from typing import Annotated, Any, Self

from pydantic import AliasChoices, BaseModel, Field, field_validator

from src.modules.reminders.domain.enums import EndOfMonthPolicy, ScheduleLogicType
from src.modules.reminders.domain.exceptions import InvalidScheduleConfigError


class DateWithMonthIntervalConfig(BaseModel):
    """Конфігурація Логіки 1: нагадування у конкретний день з інтервалом у місяцях."""

    day: Annotated[int, Field(ge=1, le=31, description="День місяця (1-31)")]
    month: Annotated[
        int | None,
        Field(default=None, ge=1, le=12, description="Місяць події (1-12, обов'язковий для річниць)"),
    ] = None
    interval_months: Annotated[
        int,
        Field(
            default=1,
            ge=1,
            le=120,
            description="Інтервал повторення у місяцях (1 для щомісячних, 12 для щорічних)",
        ),
    ] = 1
    birth_year: Annotated[
        int | None,
        Field(
            default=None,
            ge=1900,
            le=2100,
            description="Рік народження або заснування для розрахунку віку/річниці",
        ),
    ] = None
    notify_time: Annotated[
        time,
        Field(default=time(9, 0), description="Локальний час відправки сповіщення"),
    ] = time(9, 0)
    anchor_date: Annotated[
        date | None,
        Field(default=None, description="Опорна дата наступної події (опціонально)"),
    ] = None
    end_of_month_policy: Annotated[
        EndOfMonthPolicy,
        Field(
            default=EndOfMonthPolicy.LAST_DAY_OF_MONTH,
            description="Політика обробки 29-31 чисел у коротких місяцях",
        ),
    ] = EndOfMonthPolicy.LAST_DAY_OF_MONTH

    def to_dict(self) -> dict[str, Any]:
        """Серіалізує конфігурацію у чистий JSON-сумісний словник."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Створює екземпляр моделі з сирого словника."""
        return cls.model_validate(data)


class DailyAtTimesConfig(BaseModel):
    """Конфігурація Логіки 2: нагадування щодня у фіксовані години."""

    times: Annotated[list[time], Field(min_length=1, description="Список локальних годин спрацювання щодня")]

    @field_validator("times", mode="after")
    @classmethod
    def _dedup_and_sort_times(cls, v: list[time]) -> list[time]:
        """Сортує години та видаляє можливі дублікати."""
        return sorted(list(set(v)))

    def to_dict(self) -> dict[str, Any]:
        """Серіалізує конфігурацію у чистий JSON-сумісний словник."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Створює екземпляр моделі з сирого словника."""
        return cls.model_validate(data)


class ExactDateTimeDeadlineConfig(BaseModel):
    """Конфігурація Логіки 3: задача з дедлайном на точну дату та час."""

    due_datetime: Annotated[datetime, Field(description="Точна дата та час дедлайну (UTC)")]

    @field_validator("due_datetime", mode="after")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        """Гарантує UTC часовий пояс для мітки дедлайну."""
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Серіалізує конфігурацію у чистий JSON-сумісний словник."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Створює екземпляр моделі з сирого словника."""
        return cls.model_validate(data)


class ExactDateDeadlineConfig(BaseModel):
    """Конфігурація Логіки 4: задача з дедлайном на календарну дату без зазначення точної години."""

    due_date: Annotated[date, Field(description="Календарна дата дедлайну")]
    default_notify_time: Annotated[
        time,
        Field(default=time(9, 0), description="Локальний час сповіщення (за замовчуванням 09:00)"),
    ] = time(9, 0)

    def to_dict(self) -> dict[str, Any]:
        """Серіалізує конфігурацію у чистий JSON-сумісний словник."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Створює екземпляр моделі з сирого словника."""
        return cls.model_validate(data)


class IntervalDaysConfig(BaseModel):
    """Конфігурація Логіки 5: повторення через фіксовану кількість днів."""

    days: Annotated[int, Field(ge=1, le=3650, description="Інтервал повторення у днях (наприклад, 28 днів)")]
    notify_time: Annotated[
        time,
        Field(default=time(9, 0), description="Локальний час сповіщення"),
    ] = time(9, 0)
    anchor_date: Annotated[
        date | None,
        Field(default=None, description="Дата відліку або наступного циклу"),
    ] = None

    def to_dict(self) -> dict[str, Any]:
        """Серіалізує конфігурацію у чистий JSON-сумісний словник."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Створює екземпляр моделі з сирого словника."""
        return cls.model_validate(data)


class IntervalHoursConfig(BaseModel):
    """Конфігурація Логіки 6: повторення через фіксовану кількість годин."""

    interval_hours: Annotated[
        int,
        Field(
            ge=1,
            le=168,
            validation_alias=AliasChoices("interval_hours", "hours"),
            description="Інтервал повторення у годинах (наприклад, кожні 8 годин)",
        ),
    ]
    first_trigger: Annotated[
        time,
        Field(default=time(8, 0), description="Локальний час першого прийому"),
    ] = time(8, 0)

    def to_dict(self) -> dict[str, Any]:
        """Серіалізує конфігурацію у чистий JSON-сумісний словник."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Створює екземпляр моделі з сирого словника."""
        return cls.model_validate(data)


type ScheduleConfig = (
    DateWithMonthIntervalConfig
    | DailyAtTimesConfig
    | ExactDateTimeDeadlineConfig
    | ExactDateDeadlineConfig
    | IntervalDaysConfig
    | IntervalHoursConfig
)

SCHEDULE_CONFIG_MAP: dict[ScheduleLogicType, type[BaseModel]] = {
    ScheduleLogicType.DATE_WITH_MONTH_INTERVAL: DateWithMonthIntervalConfig,
    ScheduleLogicType.DAILY_AT_TIMES: DailyAtTimesConfig,
    ScheduleLogicType.EXACT_DATETIME_DEADLINE: ExactDateTimeDeadlineConfig,
    ScheduleLogicType.EXACT_DATE_DEADLINE: ExactDateDeadlineConfig,
    ScheduleLogicType.INTERVAL_DAYS: IntervalDaysConfig,
    ScheduleLogicType.INTERVAL_HOURS: IntervalHoursConfig,
}


def parse_schedule_config(
    schedule_logic: ScheduleLogicType,
    raw_config: Mapping[str, Any] | ScheduleConfig,
) -> ScheduleConfig:
    """Парсить та валідує словник або Pydantic-об'єкт конфігурації для відповідної логіки."""
    if isinstance(
        raw_config,
        (
            DateWithMonthIntervalConfig,
            DailyAtTimesConfig,
            ExactDateTimeDeadlineConfig,
            ExactDateDeadlineConfig,
            IntervalDaysConfig,
            IntervalHoursConfig,
        ),
    ):
        return raw_config

    model_cls = SCHEDULE_CONFIG_MAP.get(schedule_logic)
    if model_cls is None:
        raise InvalidScheduleConfigError(f"Невідома логіка розкладу: {schedule_logic}.")

    try:
        parsed = model_cls.model_validate(raw_config)
        return parsed  # type: ignore[return-value]
    except Exception as exc:
        raise InvalidScheduleConfigError(
            f"Помилка валідації конфігурації розкладу для {schedule_logic}: {exc}."
        ) from exc


def serialize_schedule_config(config: ScheduleConfig) -> dict[str, Any]:
    """Серіалізує конфігурацію розкладу у чистий JSON-словник для збереження у JSONB."""
    return config.model_dump(mode="json")
