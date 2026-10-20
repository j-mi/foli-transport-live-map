"""Live vehicles: a REST snapshot and a Server-Sent Events stream.

Why SSE and not WebSocket: data flows one way (server -> browser). SSE is plain HTTP, works
through ordinary proxies, and the browser's EventSource reconnects automatically. User actions
(favourites, selecting a line) are ordinary REST calls, so nothing needs a two-way socket.

Wire format of the stream:

    retry: 3000
    event: status
    data: {"upstream_status":"OK","fetched_at":"2026-10-04T11:18:12Z"}

    id: 1042
    event: vehicles
    data: {"seq":1042,"fetched_at":"...","upstream_status":"OK","vehicles":[...]}

    event: heartbeat
    data: "2026-10-04T11:18:27Z"

Every `vehicles` event carries the full snapshot (a few hundred vehicles). Deltas would save
bandwidth but bring ordering and resync problems; a possible later optimisation.
"""

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.realtime.broadcaster import Broadcaster, SnapshotMessage
from app.realtime.poller import VehiclePoller
from app.schemas import Snapshot, StatusEvent
from app.services import Services, get_services

logger = logging.getLogger(__name__)
router = APIRouter(tags=["vehicles"])

# Tells EventSource how long to wait before reconnecting after the connection drops.
RECONNECT_DELAY_MS = 3000
# Sent on idle connections so proxies do not close them, and so the browser can tell a quiet
# connection (Föli down, nothing new to send) from a dead one.
HEARTBEAT_S = 15


@router.get(
    "/vehicles",
    response_class=Response,
    responses={200: {"model": Snapshot, "content": {"application/json": {}}}},
)
async def current_vehicles(services: Annotated[Services, Depends(get_services)]) -> Response:
    """Current snapshot. Used for the first paint and as the polling fallback."""
    return Response(services.poller.message.data, media_type="application/json")


@router.get("/vehicles/stream")
async def vehicle_stream(
    services: Annotated[Services, Depends(get_services)],
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    if last_event_id:
        # We always resync with the full current snapshot (the simplest correct approach),
        # so the id is only logged to show where the client was.
        logger.info("SSE client reconnected (Last-Event-ID %s)", last_event_id)
    return EventSourceResponse(
        snapshot_events(services.poller, services.broadcaster),
        ping=HEARTBEAT_S,
        ping_message_factory=_heartbeat,
        # Belt and braces: sse-starlette sets this too. It stops nginx buffering the stream.
        headers={"X-Accel-Buffering": "no"},
    )


def _heartbeat() -> ServerSentEvent:
    # A named event instead of the usual SSE comment line (": ping"): browsers hide comments from
    # JavaScript, but the client's watchdog needs to see that the connection is still alive. A
    # connection can die without the browser noticing (a proxy or NAT silently dropping it), and
    # then EventSource would wait forever instead of reconnecting.
    return ServerSentEvent(json.dumps(datetime.now(UTC).isoformat()), event="heartbeat")


def _status_event(message: SnapshotMessage) -> ServerSentEvent:
    data = StatusEvent(upstream_status=message.upstream_status, fetched_at=message.fetched_at)
    return ServerSentEvent(data.model_dump_json(), event="status")


async def snapshot_events(
    poller: VehiclePoller, broadcaster: Broadcaster
) -> AsyncIterator[ServerSentEvent]:
    """Yield SSE events for one client until it disconnects (sse-starlette cancels us then)."""
    # Subscribe BEFORE reading the current snapshot so nothing published in between is lost.
    # If the current snapshot is also already in the queue, the seq check skips the duplicate.
    with broadcaster.subscribe() as queue:
        message = poller.message
        last_seq = -1
        last_status: str | None = None
        first = True
        while True:
            if message.seq > last_seq:
                if message.upstream_status != last_status:
                    yield _status_event(message)
                    last_status = message.upstream_status
                yield ServerSentEvent(
                    message.data,
                    event="vehicles",
                    id=str(message.seq),
                    retry=RECONNECT_DELAY_MS if first else None,
                )
                last_seq = message.seq
                first = False
            message = await queue.get()
