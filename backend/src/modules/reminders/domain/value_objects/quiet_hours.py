from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo


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

    def should_disable_sound(self, dt_utc: datetime, *, strict_schedule: bool = False) -> bool:
        """
        Визначає, чи слід вимкнути звук сповіщення:
        - Якщо strict_schedule == True: сповіщення завжди надсилається зі звуком (обхід тихих годин).
        - Якщо час у тихих годинах і strict_schedule == False: True (без звуку).
        - Якщо час поза тихими годинами: False (зі звуком).
        """
        if strict_schedule:
            return False
        return self.is_in_quiet_hours(dt_utc)
