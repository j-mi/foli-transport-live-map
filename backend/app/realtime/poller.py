"""Background task that polls Föli SIRI VM and publishes normalised snapshots.

    loop every POLL_INTERVAL_S (default 5, minimum 3):
        fetch VM through foli_client
        parse to list[Vehicle]
        build Snapshot(seq += 1, fetched_at, upstream_status, vehicles)
        store as current snapshot and broadcast it

Exactly one of these runs per backend process, however many browsers are connected. That is
the main reason the backend exists: Föli sees one polite client instead of N browsers.

Failure handling keeps the LAST GOOD vehicle positions and only changes the status. The UI can
then say "showing positions from 40 s ago" instead of going blank.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.integrations.foli_client import CircuitState, FoliClient, UpstreamError
from app.integrations.gtfs_cache import GtfsCache
from app.integrations.siri_parser import SiriParseError, parse_vehicle_monitoring
from app.realtime.broadcaster import Broadcaster, SnapshotMessage
from app.schemas import Snapshot, UpstreamStatus, Vehicle

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class VehiclePoller:
    def __init__(
        self,
        client: FoliClient,
        gtfs: GtfsCache,
        broadcaster: Broadcaster,
        interval_s: float,
        *,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._client = client
        self._gtfs = gtfs
        self._broadcaster = broadcaster
        self._interval_s = interval_s
        self._now = now

        # Before the first successful poll we have no data; "PENDING" is the honest status.
        self.snapshot = Snapshot(seq=0, fetched_at=None, upstream_status="PENDING", vehicles=[])
        self.message = self._serialise(self.snapshot)

        # Metrics exposed through /health.
        self.last_poll_at: datetime | None = None
        self.last_poll_duration_ms: float | None = None
        self.consecutive_failures = 0
        self.vehicles_skipped = 0

    async def run(self) -> None:
        """Poll forever on a fixed start-to-start schedule. Never lets an exception escape."""
        while True:
            started = time.monotonic()
            try:
                await self.poll_once()
            except Exception:  # a bug in parsing must not kill live updates for good
                logger.exception("Unexpected error in vehicle poller")
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, self._interval_s - elapsed))

    async def poll_once(self) -> None:
        self.last_poll_at = self._now()
        started = time.perf_counter()
        try:
            raw = await self._client.fetch_vehicle_monitoring()
            parsed = parse_vehicle_monitoring(raw, self._gtfs.resolve_route)
        except UpstreamError as exc:
            self.consecutive_failures += 1
            logger.warning("Vehicle poll failed (%d in a row): %s", self.consecutive_failures, exc)
            # Debounce: a single failed poll keeps the previous status, so one network blip does
            # not flash "Föli is down" in every browser. Short gaps are still visible because the
            # UI marks data stale after 20 s. Once the circuit breaker opens (5 consecutive
            # failures) we report DOWN.
            if self._client.siri_breaker.state is not CircuitState.CLOSED:
                self._update(status="DOWN")
            return
        except SiriParseError as exc:
            # Föli answered, but with something we cannot use. That is "no usable data".
            self.consecutive_failures += 1
            logger.error("Could not parse SIRI VM response: %s", exc)
            self._update(status="NO_DATA")
            return
        finally:
            self.last_poll_duration_ms = round((time.perf_counter() - started) * 1000, 1)

        self.consecutive_failures = 0
        self.vehicles_skipped = parsed.skipped
        if parsed.status == "OK":
            self._update(status="OK", vehicles=parsed.vehicles, fetched_at=self._now())
        else:
            # PENDING / NO_DATA: keep the last good positions, report the state.
            self._update(status=parsed.status)

    def _update(
        self,
        *,
        status: UpstreamStatus,
        vehicles: list[Vehicle] | None = None,
        fetched_at: datetime | None = None,
    ) -> None:
        """Publish a new snapshot if there is new data or the status changed."""
        has_new_data = vehicles is not None
        if not has_new_data and status == self.snapshot.upstream_status:
            return  # nothing a client does not already know; skip re-sending ~100 kB
        if status != self.snapshot.upstream_status:
            logger.info("Upstream status %s -> %s", self.snapshot.upstream_status, status)

        self.snapshot = Snapshot(
            seq=self.snapshot.seq + 1,
            fetched_at=fetched_at if has_new_data else self.snapshot.fetched_at,
            upstream_status=status,
            vehicles=vehicles if vehicles is not None else self.snapshot.vehicles,
        )
        self.message = self._serialise(self.snapshot)
        self._broadcaster.publish(self.message)

    @staticmethod
    def _serialise(snapshot: Snapshot) -> SnapshotMessage:
        # Serialise once here instead of once per connected client.
        return SnapshotMessage(
            seq=snapshot.seq,
            upstream_status=snapshot.upstream_status,
            fetched_at=snapshot.fetched_at,
            data=snapshot.model_dump_json(),
        )
