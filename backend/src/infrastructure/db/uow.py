from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import async_session_factory
from src.core.protocols import IUnitOfWork


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """
    Реалізація Unit of Work для SQLAlchemy 2.0 AsyncIO.

    Підтримує два режими життєвого циклу сесій:
    1. Request-Scoped: приймає відкриту зовнішню сесію `session` (наприклад, із FastAPI DI).
       Керує межами транзакції (commit/rollback), але не закриває сесію в `__aexit__`,
       делегуючи її закриття життєвому циклу HTTP-запиту.
    2. Self-Contained: ініціалізується без сесії (`session=None`) та створює власну
       сесію через `session_factory` (або глобальну `async_session_factory` за замовчуванням).
       Гарантовано закриває сесію у `__aexit__`.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = session
        self._is_external_session: bool = session is not None
        self._in_context: bool = False

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        """Вхід у контекст транзакції."""
        self._in_context = True
        if self._session is None:
            factory = self._session_factory or async_session_factory
            self._session = factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Вихід із контексту транзакції з автоматичним відкатом при помилці."""
        self._in_context = False
        try:
            if exc_type is not None:
                await self.rollback()
        finally:
            if not self._is_external_session and self._session is not None:
                await self._session.close()
                self._session = None

    async def commit(self) -> None:
        """Фіксація поточної транзакції в базі даних."""
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        """Відкат поточної транзакції."""
        if self._session is not None:
            await self._session.rollback()

    @property
    def session(self) -> AsyncSession:
        """
        Повертає поточну активну асинхронну сесію SQLAlchemy.

        Викидає RuntimeError у разі звернення поза блоком 'async with uow:'.
        """
        if not self._in_context or self._session is None:
            raise RuntimeError("UnitOfWork поза контекстом 'async with uow:'")
        return self._session
