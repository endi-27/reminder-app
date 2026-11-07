import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Self
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, BaseModel, Field, field_validator

from src.core.exceptions import ValidationException
from src.modules.reminders.domain.enums import CurrencyCode, EndOfMonthPolicy, ScheduleLogicType
from src.modules.reminders.domain.exceptions import (
    InvalidLeadTimeFormatError,
    InvalidScheduleConfigError,
)

_LEAD_TIME_PATTERN = re.compile(r"^[-+]?(\d+)([dwmhDWMH])?$")


@dataclass(frozen=True)
class Money:
    """Незмінний грошовий Value Object із захистом від float-похибок та точним квантуванням."""

    amount: Decimal
    currency: CurrencyCode = CurrencyCode.UAH

    def __post_init__(self) -> None:
        """Валідує невід'ємність суми та квантує значення до 0.01 за банківським правилом."""
        if not isinstance(self.amount, Decimal):
            try:
                dec_amount = Decimal(str(self.amount))
            except Exception as exc:
                raise ValidationException("Грошова сума має бути валідним числовим значенням.") from exc
        else:
            dec_amount = self.amount

        if dec_amount < Decimal("0.00"):
            raise ValidationException("Грошова сума не може бути від'ємною.")

        quantized = dec_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency.value}"


@dataclass(frozen=True)
class LeadTimes:
    """
    Незмінний Value Object для роботи з каскадом завчасних сповіщень.
    Зберігає нормалізовані токени у порядку спадання зміщення (наприклад, ('14d', '7d', '1d', '0d')).
    """

    items: tuple[str, ...] = field(default_factory=tuple)

    def __init__(self, raw_items: Sequence[str] | Self | None = None) -> None:
        if raw_items is None:
            object.__setattr__(self, "items", ())
            return

        if isinstance(raw_items, LeadTimes):
            object.__setattr__(self, "items", raw_items.items)
            return

        parsed_items: list[tuple[timedelta, str]] = []
        for item in raw_items:
            clean_item = item.strip()
            if not clean_item:
                continue
            td = self.parse_offset(clean_item)
            normalized_token = clean_item.lstrip("+-").lower()
            if normalized_token == "0":
                normalized_token = "0d"
            parsed_items.append((td, normalized_token))

        # Сортуємо за спаданням зміщення (від найбільшого інтервалу до найменшого)
        parsed_items.sort(key=lambda pair: pair[0], reverse=True)

        # Дедуплікація зі збереженням впорядкованості
        seen_durations: set[timedelta] = set()
        deduped: list[str] = []
        for td, token in parsed_items:
            if td not in seen_durations:
                seen_durations.add(td)
                deduped.append(token)

        object.__setattr__(self, "items", tuple(deduped))

    @staticmethod
    def parse_offset(token: str) -> timedelta:
        """
        Парсить одиничний токен інтервалу у timedelta.
        Підтримувані одиниці: 'd' (дні), 'w' (тижні), 'h' (години), 'm' (хвилини).
        Ігнорує початкові знаки '-' або '+'.
        """
        clean = token.strip()
        match = _LEAD_TIME_PATTERN.match(clean)
        if not match:
            raise InvalidLeadTimeFormatError(
                f"Некоректний формат завчасного сповіщення: '{token}'. "
                "Очікується формат виду '14d', '7d', '2h', '30m' або '0d'."
            )

        val_str, unit = match.groups()
        value = int(val_str)

        if unit is None:
            if value == 0:
                return timedelta(0)
            raise InvalidLeadTimeFormatError(
                f"Не вказано одиницю часу для зміщення '{token}'. Використовуйте 'd', 'w', 'h' або 'm'."
            )

        unit_lower = unit.lower()
        if unit_lower == "d":
            return timedelta(days=value)
        if unit_lower == "w":
            return timedelta(weeks=value)
        if unit_lower == "h":
            return timedelta(hours=value)
        if unit_lower == "m":
            return timedelta(minutes=value)

        raise InvalidLeadTimeFormatError(f"Невідома одиниця вимірювання часу у токені '{token}'.")

    def offsets(self) -> list[timedelta]:
        """Повертає список часових зміщень timedelta, відсортований за спаданням."""
        return [self.parse_offset(item) for item in self.items]

    def to_list(self) -> list[str]:
        """Повертає канонічний список рядків зміщень."""
        return list(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return len(self.items) > 0

    def __iter__(self) -> Iterator[str]:
        return iter(self.items)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            clean = item.strip().lstrip("+-").lower()
            if clean == "0":
                clean = "0d"
            return clean in self.items
        return False


@dataclass(frozen=True)
class QuietHoursWindow:
    """Параметри вікна тихих годин користувача із підтримкою нічного переходу через північ."""

    start_time: time
    end_time: time
    timezone_name: str = "Europe/Kyiv"

    def _get_zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def is_in_quiet_hours(self, dt_utc: datetime) -> bool:
        """Перевіряє, чи потрапляє зазначений UTC-момент у вікно тиші користувача."""
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=UTC)

        local_dt = dt_utc.astimezone(self._get_zone())
        t = local_dt.time().replace(tzinfo=None)

        if self.start_time == self.end_time:
            return False

        if self.start_time > self.end_time:
            # Нічний перехід через північ (наприклад, 23:00 -> 08:00)
            return t >= self.start_time or t < self.end_time

        # Денне вікно в межах однієї доби (наприклад, 01:00 -> 06:00)
        return self.start_time <= t < self.end_time

    def adjust_trigger_time(self, dt_utc: datetime, *, strict_schedule: bool = False) -> datetime:
        """
        Коригує час спрацювання сповіщення:
        - Якщо strict_schedule == True або час поза тихими годинами: повертає dt_utc без змін.
        - Якщо час у тихих годинах і strict_schedule == False: переносить на end_time + 5 хвилин.
        """
        if strict_schedule:
            return dt_utc

        if not self.is_in_quiet_hours(dt_utc):
            return dt_utc

        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=UTC)

        local_zone = self._get_zone()
        local_dt = dt_utc.astimezone(local_zone)
        local_date = local_dt.date()

        if self.start_time > self.end_time:
            # Якщо час після початку тиші перед північчю (наприклад, 23:30) — кінець тиші завтра
            if local_dt.time().replace(tzinfo=None) >= self.start_time:
                target_date = local_date + timedelta(days=1)
            else:
                # Якщо час після півночі (наприклад, 02:00) — кінець тиші сьогодні
                target_date = local_date
        else:
            target_date = local_date

        target_local = datetime.combine(target_date, self.end_time, tzinfo=local_zone) + timedelta(minutes=5)
        return target_local.astimezone(UTC)


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
