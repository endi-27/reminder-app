from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption

from src.core.exceptions import ResourceLockedException
from src.infrastructure.db.base import IdentifiableModelProtocol
from src.infrastructure.db.mappers import BaseMapper


class SqlAlchemyBaseReadRepository[TDomain, TModel: IdentifiableModelProtocol]:
    """Базовий репозиторій операцій читання через SQLAlchemy 2.0."""

    _model_cls: type[TModel]
    _mapper: BaseMapper[TDomain, TModel] | type[BaseMapper[TDomain, TModel]]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _get_mapper(self) -> BaseMapper[TDomain, TModel]:
        """Повертає інстанс мапера."""
        if isinstance(self._mapper, type):
            return self._mapper()
        return self._mapper

    def _to_domain(self, model: TModel) -> TDomain:
        """Конвертація ORM-моделі у доменну сутність через зареєстрований Data Mapper."""
        return self._get_mapper().to_domain(model)

    def _default_options(self) -> Sequence[ExecutableOption]:
        """Опції жадібного завантаження зв'язків за замовчуванням (перевизначається за потреби)."""
        return ()

    def _apply_active_filter(self, stmt: Select[TModel]) -> Select[TModel]:
        """Фільтрація активних записів без мітки м'якого видалення (deleted_at IS NULL)."""
        deleted_col = getattr(self._model_cls, "deleted_at", None)
        if deleted_col is not None:
            stmt = stmt.where(deleted_col.is_(None))
        return stmt

    async def get_by_id(self, entity_id: UUID, *, include_deleted: bool = False) -> TDomain | None:
        """Отримання сутності за первинним ключем (UUIDv7)."""
        stmt = select(self._model_cls).options(*self._default_options()).where(self._model_cls.id == entity_id)
        if not include_deleted:
            stmt = self._apply_active_filter(stmt)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm is not None else None

    async def exists_by_id(self, entity_id: UUID, *, include_deleted: bool = False) -> bool:
        """Швидка оптимізована перевірка наявності запису за його UUID через SELECT 1."""
        stmt = select(1).where(self._model_cls.id == entity_id)
        if not include_deleted:
            deleted_col = getattr(self._model_cls, "deleted_at", None)
            if deleted_col is not None:
                stmt = stmt.where(deleted_col.is_(None))
        stmt = stmt.limit(1)
        result = await self._session.execute(stmt)
        return bool(result.scalar() is not None)


class SqlAlchemyBaseCrudRepository[TDomain, TModel: IdentifiableModelProtocol](
    SqlAlchemyBaseReadRepository[TDomain, TModel]
):
    """Базовий репозиторій для повного циклу операцій (CRUD) з доменними агрегатами."""

    def _to_model(self, entity: TDomain) -> TModel:
        """Конвертація доменного агрегата в ORM-модель через зареєстрований Data Mapper."""
        return self._get_mapper().to_model(entity)

    async def save(self, entity: TDomain, /) -> None:
        """Збереження або оновлення доменного агрегата в базі даних."""
        model = self._to_model(entity)
        await self._session.merge(model)
        await self._session.flush()

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        """
        Фізичне видалення (Hard Delete) запису за його ідентифікатором UUID.

        Використовує session.get() + session.delete() для правильного виконання
        каскадів ORM та перевірки обмежень зовнішніх ключів.
        """
        orm = await self._session.get(self._model_cls, entity_id)
        if orm is not None:
            await self._session.delete(orm)
            try:
                await self._session.flush()
            except IntegrityError as exc:
                pgcode = getattr(exc.orig, "sqlstate", getattr(exc.orig, "pgcode", None))
                if pgcode == "23503" or "foreign key" in str(exc).lower():
                    raise ResourceLockedException(
                        "Неможливо остаточно видалити запис, оскільки він використовується в пов'язаних даних."
                    ) from exc
                raise
            return True
        return False
