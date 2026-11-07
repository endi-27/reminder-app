from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy import Column, DateTime, Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from src.core.exceptions import ResourceLockedException
from src.infrastructure.db.base import Base, SoftDeleteMixin, UUIDPrimaryKeyMixin
from src.infrastructure.db.mappers import BaseMapper
from src.infrastructure.db.queries import BaseQueryService, escape_like
from src.infrastructure.db.repositories import (
    SqlAlchemyBaseCrudRepository,
    SqlAlchemyBaseReadRepository,
)


class DummyEntity:
    """Фіктивна доменна сутність для тестування репозиторіїв."""

    def __init__(self, id: UUID, title: str) -> None:
        self.id = id
        self.title = title


class DummyModel(Base, UUIDPrimaryKeyMixin, SoftDeleteMixin):
    """Фіктивна ORM модель із підтримкою м'якого видалення."""

    __tablename__ = "dummy_models"

    title: Mapped[str] = mapped_column(String(100), nullable=False)


class DummyMapper(BaseMapper[DummyEntity, DummyModel]):
    """Мапер між DummyEntity та DummyModel."""

    def to_domain(self, model: DummyModel) -> DummyEntity:
        return DummyEntity(id=model.id, title=str(model.title))

    def to_model(self, entity: DummyEntity) -> DummyModel:
        model = DummyModel()
        model.id = entity.id
        model.title = entity.title
        return model


class DummyReadRepository(SqlAlchemyBaseReadRepository[DummyEntity, DummyModel]):
    """Репозиторій читання фіктивних сутностей."""

    _model_cls = DummyModel
    _mapper = DummyMapper()


class DummyCrudRepository(SqlAlchemyBaseCrudRepository[DummyEntity, DummyModel]):
    """CRUD репозиторій фіктивних сутностей."""

    _model_cls = DummyModel
    _mapper = DummyMapper()


class TestRepositories:
    """Тести базових класів репозиторіїв SQLAlchemy."""

    @pytest.mark.asyncio
    async def test_read_repository_get_by_id_found(self) -> None:
        """Перевірка успішного отримання сутності за id."""
        session = AsyncMock(spec=AsyncSession)
        entity_id = uuid7()
        orm_mock = DummyModel()
        orm_mock.id = entity_id
        orm_mock.title = "Купити молоко"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm_mock
        session.execute.return_value = mock_result

        repo = DummyReadRepository(session)
        entity = await repo.get_by_id(entity_id)

        assert entity is not None
        assert entity.id == entity_id
        assert entity.title == "Купити молоко"
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_read_repository_get_by_id_not_found(self) -> None:
        """Перевірка повернення None, якщо сутність відсутня в БД."""
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = DummyReadRepository(session)
        entity = await repo.get_by_id(uuid7())

        assert entity is None

    @pytest.mark.asyncio
    async def test_read_repository_exists_by_id(self) -> None:
        """Перевірка методу exists_by_id."""
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        session.execute.return_value = mock_result

        repo = DummyReadRepository(session)
        exists = await repo.exists_by_id(uuid7())

        assert exists is True

    @pytest.mark.asyncio
    async def test_crud_repository_save(self) -> None:
        """Перевірка методу save: викликає merge та flush."""
        session = AsyncMock(spec=AsyncSession)
        repo = DummyCrudRepository(session)

        entity = DummyEntity(id=uuid7(), title="Нове завдання")
        await repo.save(entity)

        session.merge.assert_awaited_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_crud_repository_delete_by_id_success(self) -> None:
        """Перевірка успішного фізичного видалення запису."""
        session = AsyncMock(spec=AsyncSession)
        orm_mock = DummyModel()
        session.get.return_value = orm_mock

        repo = DummyCrudRepository(session)
        result = await repo.delete_by_id(uuid7())

        assert result is True
        session.delete.assert_awaited_once_with(orm_mock)
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_crud_repository_delete_by_id_not_found(self) -> None:
        """Перевірка видалення, коли запис не знайдено (повертає False)."""
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = None

        repo = DummyCrudRepository(session)
        result = await repo.delete_by_id(uuid7())

        assert result is False
        session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_crud_repository_delete_by_id_foreign_key_violation(self) -> None:
        """Перевірка перехоплення помилки зовнішнього ключа та підняття ResourceLockedException."""
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = DummyModel()

        orig_error = MagicMock()
        orig_error.pgcode = "23503"
        orig_error.sqlstate = "23503"
        session.flush.side_effect = IntegrityError(
            statement="DELETE FROM dummy_models ...",
            params={},
            orig=orig_error,
        )

        repo = DummyCrudRepository(session)
        with pytest.raises(ResourceLockedException, match="Неможливо остаточно видалити запис"):
            await repo.delete_by_id(uuid7())


class ConcreteQueryService(BaseQueryService):
    """Конкретний сервіс запитів для перевірки методів BaseQueryService."""


class TestBaseQueryService:
    """Тести базового класу вибірок BaseQueryService та escape_like."""

    def test_escape_like(self) -> None:
        """Перевірка екранування спецсимволів LIKE (%, _, \\)."""
        raw = "100%_тест\\приклад"
        escaped = escape_like(raw)
        assert escaped == "100\\%\\_тест\\\\приклад"
        assert ConcreteQueryService._escape_like(raw) == "100\\%\\_тест\\\\приклад"

    def test_apply_date_range_datetime(self) -> None:
        """Перевірка застосування фільтра дат з об'єктами datetime."""
        session = AsyncMock(spec=AsyncSession)
        service = ConcreteQueryService(session)

        col = Column("created_at", DateTime(timezone=True))
        stmt = select(col)

        dt_from = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        dt_to = datetime(2026, 1, 10, 18, 0, 0, tzinfo=UTC)

        filtered = service._apply_date_range(stmt, col, date_from=dt_from, date_to=dt_to)
        sql = str(filtered)
        assert "created_at >=" in sql
        assert "created_at <=" in sql

    def test_apply_date_range_date(self) -> None:
        """Перевірка застосування фільтра дат з об'єктами date (напіввідкритий інтервал)."""
        session = AsyncMock(spec=AsyncSession)
        service = ConcreteQueryService(session)

        col = Column("created_at", DateTime(timezone=True))
        stmt = select(col)

        d_from = date(2026, 5, 1)
        d_to = date(2026, 5, 5)

        filtered = service._apply_date_range(stmt, col, date_from=d_from, date_to=d_to)
        sql = str(filtered)
        assert "created_at >=" in sql
        assert "created_at <" in sql

    @pytest.mark.asyncio
    async def test_count_total(self) -> None:
        """Перевірка підрахунку загальної кількості записів через _count_total."""
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        session.execute.return_value = mock_result

        service = ConcreteQueryService(session)
        col = Column("id", Integer)
        stmt = select(col).order_by(col.desc())

        total = await service._count_total(stmt)
        assert total == 42
        session.execute.assert_awaited_once()
