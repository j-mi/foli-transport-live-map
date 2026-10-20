"""The long-lived objects the app needs, built once at startup and shared by all requests."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.integrations.foli_client import FoliClient
from app.integrations.gtfs_cache import GtfsCache
from app.realtime.broadcaster import Broadcaster
from app.realtime.poller import VehiclePoller
from app.schemas import DeparturesResponse
from app.stop_sync import StopSync
from app.ttl_cache import TtlCache


@dataclass
class Services:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient
    foli: FoliClient
    gtfs: GtfsCache
    broadcaster: Broadcaster
    poller: VehiclePoller
    stop_sync: StopSync
    # Departures per stop, shared by every client for 15 s: however many people have the same
    # stop open, Föli sees at most one stop-monitoring request per stop per 15 s.
    departures: TtlCache[DeparturesResponse]

    async def aclose(self) -> None:
        await self.http.aclose()
        await self.engine.dispose()


def build_services(settings: Settings) -> Services:
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    http = FoliClient.build_http_client(settings.user_agent)
    foli = FoliClient(http, settings.foli_base_url)
    gtfs = GtfsCache(foli)
    stop_sync = StopSync(sessionmaker, gtfs)
    gtfs.on_dataset_loaded = stop_sync.on_dataset_loaded
    broadcaster = Broadcaster(queue_size=2)
    poller = VehiclePoller(foli, gtfs, broadcaster, settings.poll_interval_s)
    return Services(
        settings=settings,
        engine=engine,
        sessionmaker=sessionmaker,
        http=http,
        foli=foli,
        gtfs=gtfs,
        broadcaster=broadcaster,
        poller=poller,
        stop_sync=stop_sync,
        departures=TtlCache(ttl_s=15),
    )


def get_services(request: Request) -> Services:
    return request.app.state.services


async def get_session(
    services: Annotated[Services, Depends(get_services)],
) -> AsyncIterator[AsyncSession]:
    async with services.sessionmaker() as session:
        yield session
