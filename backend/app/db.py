"""Async SQLAlchemy engine and session factory."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def create_engine(database_url: str) -> AsyncEngine:
    # pool_pre_ping: transparently replace connections the database closed (e.g. after a
    # Postgres restart) instead of failing the first request that picks one up.
    # timeout: asyncpg waits 60 s for a connection by default; fail fast instead so requests
    # get a clear 503 rather than hanging when the database is unreachable.
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"timeout": 5, "command_timeout": 10},
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def database_is_reachable(engine: AsyncEngine, timeout_s: float = 2.0) -> bool:
    try:
        async with asyncio.timeout(timeout_s):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False
