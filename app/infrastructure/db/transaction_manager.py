from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.transaction_manager import TransactionManager


class SQLAlchemyTransactionManager(TransactionManager):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def start(self) -> AsyncIterator[None]:
        if self._session.in_transaction():
            yield
        else:
            async with self._session.begin():
                yield
