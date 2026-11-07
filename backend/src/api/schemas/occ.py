from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class VersionedUpdateSchema(BaseModel):
    """Базова схема для операцій оновлення даних з оптимістичним блокуванням (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Поточна версія запису для оптимістичного блокування (OCC)"),
    ]
