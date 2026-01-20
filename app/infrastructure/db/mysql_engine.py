from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


def build_engine(settings: Settings):
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for SQL mode")
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


def build_sessionmaker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(session_maker) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        async with session.begin():
            yield session
