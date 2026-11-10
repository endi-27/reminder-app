import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Self

from src.modules.reminders.domain.exceptions import InvalidLeadTimeFormatError

_LEAD_TIME_PATTERN = re.compile(r"^[-+]?(\d+)([dwmhDWMH])?$")


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
