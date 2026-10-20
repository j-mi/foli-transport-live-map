"""Alembic environment, async flavour (asyncpg).

Migrations are hand-written SQL-first (see versions/), so `target_metadata` is only used if you
try autogenerate. Spatial columns and indexes are clearer as explicit SQL anyway.
"""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def _url() -> str:
    # Tests (and tools) can pass an explicit URL via `config.set_main_option("sqlalchemy.url")`.
    explicit = context.config.get_main_option("sqlalchemy.url")
    if explicit:
        return explicit
    settings = get_settings()
    return settings.migrations_database_url or settings.database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
