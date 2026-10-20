"""Keeps the PostGIS `stops` table in step with the GTFS dataset held in memory.

The in-memory GTFS cache is the source of truth; this copy exists only so PostgreSQL can answer
spatial questions with a spatial index. A small background loop syncs it whenever the dataset id
changes, and retries if the database is unavailable, so a database that starts after the
backend (or restarts) is caught up within `retry_s` seconds.
"""

import asyncio
import logging
from contextlib import suppress

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.gtfs_cache import GtfsCache, GtfsDataset

logger = logging.getLogger(__name__)

_UPSERT = text(
    """
    INSERT INTO stops (stop_id, name, geom, dataset_id)
    VALUES (:stop_id, :name, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :dataset_id)
    ON CONFLICT (stop_id) DO UPDATE
        SET name = EXCLUDED.name, geom = EXCLUDED.geom, dataset_id = EXCLUDED.dataset_id
    """
)


async def sync_stops(sessionmaker: async_sessionmaker[AsyncSession], dataset: GtfsDataset) -> bool:
    """Upsert every stop of `dataset` and delete stops from older datasets.

    Returns False when the table already holds this dataset (e.g. after a backend restart).
    """
    async with sessionmaker() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM stops WHERE dataset_id = :ds"),
            {"ds": dataset.dataset_id},
        )
        if count == len(dataset.stops):
            return False
        rows = [
            {
                "stop_id": s.stop_id,
                "name": s.name,
                "lat": s.lat,
                "lon": s.lon,
                "dataset_id": dataset.dataset_id,
            }
            for s in dataset.stops.values()
        ]
        await session.execute(_UPSERT, rows)  # executemany: one round trip per batch
        await session.execute(
            text("DELETE FROM stops WHERE dataset_id <> :ds"), {"ds": dataset.dataset_id}
        )
        await session.commit()
    logger.info("Synced %d stops of dataset %s into PostGIS", len(rows), dataset.dataset_id)
    return True


class StopSync:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], gtfs: GtfsCache) -> None:
        self._sessionmaker = sessionmaker
        self._gtfs = gtfs
        self._wake = asyncio.Event()
        self.synced_dataset_id: str | None = None

    async def on_dataset_loaded(self, _: GtfsDataset) -> None:
        """GtfsCache callback: wake the loop instead of syncing inline, so a slow or missing
        database never delays the GTFS load itself."""
        self._wake.set()

    async def run(self, retry_s: float = 30.0) -> None:
        while True:
            dataset = self._gtfs.dataset
            if dataset and dataset.dataset_id != self.synced_dataset_id:
                try:
                    await sync_stops(self._sessionmaker, dataset)
                    self.synced_dataset_id = dataset.dataset_id
                except Exception as exc:
                    logger.warning("Could not sync stops to PostGIS (retrying): %s", exc)
            self._wake.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=retry_s)
