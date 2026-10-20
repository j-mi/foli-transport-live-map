"""Shared test helpers. Tests never call the live Föli API: every HTTP call is mocked with respx
and answered from the recorded samples in tests/fixtures/ (see scripts/fetch_fixtures.py)."""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
import respx
from alembic.config import Config as AlembicConfig
from sqlalchemy import text

from alembic import command as alembic_command
from app.config import Settings
from app.main import create_app
from app.services import Services, build_services

FIXTURES = Path(__file__).parent / "fixtures"
FOLI = "https://data.foli.fi"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def dataset_id() -> str:
    return load_fixture("gtfs_index.json")["latest"]


@pytest.fixture
def foli_mock() -> Iterator[respx.MockRouter]:
    """Föli answered from fixtures. Individual tests can override routes."""
    ds = dataset_id()
    with respx.mock(base_url=FOLI, assert_all_called=False) as mock:
        mock.get("/gtfs/").respond(json=load_fixture("gtfs_index.json"))
        mock.get(f"/gtfs/v0/{ds}/routes").respond(json=load_fixture("gtfs_routes.json"))
        mock.get(f"/gtfs/v0/{ds}/stops").respond(json=load_fixture("gtfs_stops.json"))
        mock.get(f"/gtfs/v0/{ds}/trips/route/1", name="trips_route_1").respond(
            json=load_fixture("gtfs_trips_route_1.json")
        )
        for shape_id in ("1", "2", "5", "6"):
            mock.get(f"/gtfs/v0/{ds}/shapes/{shape_id}").respond(
                json=load_fixture(f"gtfs_shape_{shape_id}.json")
            )
        mock.get("/siri/vm").respond(json=load_fixture("siri_vm.json"))
        mock.get("/siri/sm/1", name="sm_stop_1").respond(json=load_fixture("siri_sm_stop.json"))
        yield mock


def test_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "start_background_tasks": False,
        "foli_base_url": FOLI,
        # Nothing listens on port 1, so DB-dependent code fails fast unless a test opts in.
        "database_url": "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
async def services(foli_mock: respx.MockRouter) -> AsyncIterator[Services]:
    services = build_services(test_settings())
    await services.gtfs.refresh()
    yield services
    await services.aclose()


@pytest.fixture
async def api(services: Services) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client for the app, with services installed directly (no lifespan, no tasks)."""
    app = create_app(services.settings)
    app.state.services = services
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# -- Database fixtures (tests marked `db`) ------------------------------------------------------
# Run against the compose database:  docker compose up -d db  &&  .venv/bin/pytest
# A separate `transport_test` database is created (and migrated) for the test session, so the
# development data is never touched. Without a reachable database these tests are skipped.

TEST_DB_ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL", "postgresql://transport:change_me@localhost:5432/postgres"
)
TEST_DB_NAME = "transport_test"


@pytest.fixture(scope="session")
async def db_url() -> AsyncIterator[str]:
    try:
        admin = await asyncpg.connect(TEST_DB_ADMIN_URL, timeout=3)
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        pytest.skip(f"PostGIS not reachable ({exc}); start it with `docker compose up -d db`")
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await admin.close()

    base = TEST_DB_ADMIN_URL.rsplit("/", 1)[0].replace("postgresql://", "postgresql+asyncpg://")
    url = f"{base}/{TEST_DB_NAME}"
    config = AlembicConfig(str(Path(__file__).parent.parent / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    # Alembic's env.py runs its own event loop, so run it in a worker thread.
    await asyncio.to_thread(alembic_command.upgrade, config, "head")
    yield url


@pytest.fixture
async def db_services(foli_mock: respx.MockRouter, db_url: str) -> AsyncIterator[Services]:
    services = build_services(test_settings(database_url=db_url))
    async with services.engine.begin() as conn:
        await conn.execute(text("TRUNCATE favourite_stops, favourite_lines, stops"))
    await services.gtfs.refresh()
    yield services
    await services.aclose()


@pytest.fixture
async def db_api(db_services: Services) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(db_services.settings)
    app.state.services = db_services
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
