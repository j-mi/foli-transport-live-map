from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.db import database_is_reachable
from app.schemas import HealthResponse
from app.services import Services, get_services

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    response: Response, services: Annotated[Services, Depends(get_services)]
) -> HealthResponse:
    """Liveness plus the facts an operator wants at a glance.

    Returns 503 only when OUR dependency (the database) is broken. Föli being down is reported
    as `degraded` with 200: the backend itself is healthy and still serving last known data.
    """
    db_ok = await database_is_reachable(services.engine)
    poller = services.poller
    snapshot = poller.snapshot
    if not db_ok:
        response.status_code = 503
    return HealthResponse(
        status="ok" if db_ok and snapshot.upstream_status == "OK" else "degraded",
        database="ok" if db_ok else "error",
        upstream_status=snapshot.upstream_status,
        gtfs_dataset_id=services.gtfs.dataset_id,
        vehicle_count=len(snapshot.vehicles),
        snapshot_seq=snapshot.seq,
        snapshot_fetched_at=snapshot.fetched_at,
        last_poll_at=poller.last_poll_at,
        last_poll_duration_ms=poller.last_poll_duration_ms,
        consecutive_poll_failures=poller.consecutive_failures,
        circuit_state=services.foli.siri_breaker.state.value,
        sse_clients=services.broadcaster.subscriber_count,
    )
