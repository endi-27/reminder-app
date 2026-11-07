from dataclasses import dataclass
from datetime import UTC, datetime

from src.core.domain.base import BaseEntity
from src.core.exceptions import (
    InactiveEntityError,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
)


@dataclass(kw_only=True)
class AggregateRoot(BaseEntity):
    """
    Базовий корінь агрегата (DDD) із підтримкою оптимістичного блокування (OCC)
    та життєвого циклу м'якого видалення (Soft Delete).
    """

    version: int = 1
    deleted_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Перевіряє, чи є агрегат активним (не позначеним як видалений)."""
        return self.deleted_at is None

    def ensure_active(
        self,
        action_phrase: str = "виконати дію над деактивованим ресурсом",
        restore_hint: str = "Спочатку відновіть його.",
    ) -> None:
        """Перевіряє активність агрегата для запобігання мутацій деактивованих об'єктів."""
        if not self.is_active:
            clean_action = action_phrase.strip().rstrip(".")
            hint = f" {restore_hint.strip()}" if restore_hint else ""
            raise InactiveEntityError(f"Неможливо {clean_action}.{hint}".strip())

    def soft_delete(self) -> None:
        """М'яке видалення (деактивація) агрегата з оновленням міток часу."""
        if not self.is_active:
            raise ResourceAlreadyInactiveException("Цей ресурс вже є неактивним.")

        now = datetime.now(UTC)
        self.deleted_at = now
        self.updated_at = now

    def restore(self) -> None:
        """Відновлення агрегата з деактивованого стану."""
        if self.is_active:
            raise ResourceAlreadyActiveException("Цей ресурс вже є активним.")

        self.deleted_at = None
        self.updated_at = datetime.now(UTC)
