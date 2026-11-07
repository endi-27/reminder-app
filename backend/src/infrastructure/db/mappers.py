from typing import Protocol


class BaseMapper[TDomain, TModel](Protocol):
    """Абстрактний протокол мапера між чистими доменними агрегатами та ORM-моделями SQLAlchemy."""

    def to_domain(self, model: TModel) -> TDomain:
        """Трансформація ORM-моделі у відповідний чистий доменний агрегат."""
        ...

    def to_model(self, entity: TDomain) -> TModel:
        """Трансформація чистого доменного агрегата в ORM-модель для збереження в БД."""
        ...
