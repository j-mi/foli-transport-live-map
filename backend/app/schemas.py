"""Pydantic models for everything the API returns.

These are our own clean domain model. Föli's SIRI/GTFS field names never leak past the
`integrations` package. The frontend mirrors these in `frontend/src/api/types.ts`.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# OK       - fresh data from Föli
# PENDING  - Föli's SIRI service is starting; data expected in 5-30 s
# NO_DATA  - Föli answered but reported NO_SIRI_DATA (problem on their side)
# DOWN     - we could not reach Föli repeatedly (circuit breaker open)
UpstreamStatus = Literal["OK", "PENDING", "NO_DATA", "DOWN"]


class Vehicle(BaseModel):
    id: str = Field(description="Föli vehicleref")
    line: str | None = Field(description="Line number as shown to passengers, e.g. '14'")
    route_id: str | None = Field(description="GTFS route_id, or null if the line is unknown")
    direction: str | None
    destination: str | None
    lat: float
    lon: float
    delay_s: int | None = Field(description="Seconds behind schedule; negative means early")
    next_stop: str | None
    recorded_at: datetime
    monitored: bool


class Snapshot(BaseModel):
    seq: int = Field(description="Increments on every published snapshot; used as the SSE id")
    fetched_at: datetime | None = Field(
        description="When the vehicle data was fetched from Föli. Null before the first success."
    )
    upstream_status: UpstreamStatus
    vehicles: list[Vehicle]


class StatusEvent(BaseModel):
    """Payload of the SSE `status` event, sent whenever `upstream_status` changes."""

    upstream_status: UpstreamStatus
    fetched_at: datetime | None


class Line(BaseModel):
    route_id: str
    short_name: str
    long_name: str
    color: str | None = Field(description="Hex colour without '#', when Föli provides one")
    text_color: str | None


class LinesResponse(BaseModel):
    dataset_id: str
    lines: list[Line]


class FavouriteStop(BaseModel):
    stop_id: str
    name: str
    lat: float
    lon: float
    created_at: datetime


class FavouriteLine(BaseModel):
    route_id: str
    short_name: str
    created_at: datetime


class Favourites(BaseModel):
    stops: list[FavouriteStop]
    lines: list[FavouriteLine]


class NearbyStop(BaseModel):
    stop_id: str
    name: str
    lat: float
    lon: float
    distance_m: float


class NearbyStopsResponse(BaseModel):
    lat: float
    lon: float
    radius_m: float
    stops: list[NearbyStop]


class Departure(BaseModel):
    line: str | None
    route_id: str | None
    destination: str | None
    aimed_departure: datetime | None
    expected_departure: datetime | None
    monitored: bool
    vehicle_id: str | None


class DeparturesResponse(BaseModel):
    stop_id: str
    fetched_at: datetime
    departures: list[Departure]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    upstream_status: UpstreamStatus
    gtfs_dataset_id: str | None
    vehicle_count: int
    snapshot_seq: int
    snapshot_fetched_at: datetime | None
    last_poll_at: datetime | None
    last_poll_duration_ms: float | None
    consecutive_poll_failures: int
    circuit_state: str
    sse_clients: int


GeoJSON = dict[str, Any]
