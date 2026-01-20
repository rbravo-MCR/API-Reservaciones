from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol


class TransactionManager(Protocol):
    @asynccontextmanager
    async def start(self) -> AsyncIterator[None]:
        yield
