from contextlib import asynccontextmanager

from app.application.interfaces.transaction_manager import TransactionManager


class NoopTransactionManager(TransactionManager):
    @asynccontextmanager
    async def start(self):
        yield
