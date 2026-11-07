from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(kw_only=True)
class BaseEntity:
    """Базова доменна сутність з ідентифікатором та часовими мітками створення і модифікації."""

    id: UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def mark_updated(self) -> None:
        """Оновлює часову мітку модифікації сутності."""
        self.updated_at = datetime.now(UTC)
