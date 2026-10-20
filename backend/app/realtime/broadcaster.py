"""In-memory fan-out of vehicle snapshots to connected SSE clients.

One poller produces a snapshot every few seconds; any number of browsers want it. Each
subscriber gets its own small bounded queue:

    poller --publish()--> [queue A] --> SSE response for browser A
                     \--> [queue B] --> SSE response for browser B (slow mobile connection)

`publish()` never awaits, so it can never be blocked by a client. If a client's queue is full
(it is not reading fast enough), we drop the OLDEST item in that queue. That is safe because
every message is a complete snapshot: a client only ever needs the newest one, never the
history. A slow client therefore just sees fewer updates; everyone else is unaffected.

Scaling note: this works for a single backend process. With several replicas each would poll
Föli on its own; the fix would be one poller publishing through Redis pub/sub (or similar) and
every replica subscribing. Deliberately not built here.
"""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotMessage:
    seq: int
    upstream_status: str
    fetched_at: datetime | None
    # The snapshot serialised to JSON exactly once, shared by every subscriber.
    data: str


class Broadcaster:
    def __init__(self, queue_size: int = 2) -> None:
        self._queue_size = queue_size
        self._queues: set[asyncio.Queue[SnapshotMessage]] = set()
        self.dropped_messages = 0

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[SnapshotMessage]]:
        queue: asyncio.Queue[SnapshotMessage] = asyncio.Queue(maxsize=self._queue_size)
        self._queues.add(queue)
        logger.info("SSE client connected (%d total)", len(self._queues))
        try:
            yield queue
        finally:
            self._queues.discard(queue)
            logger.info("SSE client disconnected (%d total)", len(self._queues))

    def publish(self, message: SnapshotMessage) -> None:
        for queue in list(self._queues):
            if queue.full():
                try:
                    queue.get_nowait()  # drop the oldest; the newest snapshot supersedes it
                    self.dropped_messages += 1
                except asyncio.QueueEmpty:  # pragma: no cover - cannot happen single-threaded
                    pass
            queue.put_nowait(message)
