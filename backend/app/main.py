"""FastAPI app factory. The lifespan starts and stops the background tasks.

Background tasks (one of each per process):
- GTFS refresher: loads routes and stops on startup, checks for a new dataset every 6 h.
- Vehicle poller: polls SIRI VM every 5 s and broadcasts snapshots to SSE clients.
- Stop sync: copies GTFS stops into PostGIS whenever the dataset changes.

Startup does NOT wait for Föli. If Föli is down when we start, the API is still up, serves
clear 503s for static data and an honest PENDING/DOWN status for vehicles, and recovers on its
own when Föli comes back.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api import favourites, health, lines, stops, vehicles
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.services import build_services

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Tests may install their own services before the app starts.
        if getattr(app.state, "services", None) is None:
            app.state.services = build_services(settings)
        services = app.state.services

        tasks: list[asyncio.Task[None]] = []
        if settings.start_background_tasks:
            refresh_s = settings.gtfs_refresh_hours * 3600
            tasks.append(asyncio.create_task(services.gtfs.run_refresh_loop(refresh_s)))
            tasks.append(asyncio.create_task(services.poller.run()))
            tasks.append(asyncio.create_task(services.stop_sync.run()))
            logger.info(
                "Started GTFS refresher and vehicle poller (every %.0f s)", settings.poll_interval_s
            )
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await services.aclose()

    app = FastAPI(
        title="Föli live map API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    install_error_handlers(app)

    # CORS is only needed when the frontend is served from another origin (e.g. Vite without
    # its proxy). Restricted to the configured origins; never "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    # Compress JSON (the stops GeoJSON shrinks ~5x). Starlette skips text/event-stream by
    # default, which matters: compressing SSE would buffer events.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    for module in (health, lines, stops, vehicles, favourites):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
