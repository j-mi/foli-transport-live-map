import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import gtfs_not_ready, not_found, upstream_unavailable
from app.integrations.foli_client import UpstreamClientError, UpstreamError
from app.integrations.gtfs_cache import GtfsNotReady
from app.integrations.siri_parser import SiriParseError, parse_stop_monitoring
from app.schemas import DeparturesResponse, NearbyStop, NearbyStopsResponse
from app.services import Services, get_services, get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stops"])

ServicesDep = Annotated[Services, Depends(get_services)]
StopId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


@router.get("/stops", response_class=Response)
async def list_stops(services: ServicesDep) -> Response:
    """All stops as a GeoJSON FeatureCollection, serialised once per GTFS dataset."""
    try:
        dataset = services.gtfs.require_dataset()
    except GtfsNotReady:
        raise gtfs_not_ready() from None
    return Response(
        dataset.stops_geojson,
        media_type="application/geo+json",
        headers={"X-GTFS-Dataset": dataset.dataset_id},
    )


# Distances in metres need the geography type (on a sphere), not geometry (planar degrees).
# ST_MakePoint takes (longitude, latitude): x before y. The `geom::geography` expression matches
# the stops_geog_gist expression index, so ST_DWithin can use the index (see migration 0002).
_NEARBY_SQL = text(
    """
    SELECT stop_id, name, ST_Y(geom) AS lat, ST_X(geom) AS lon,
           ST_Distance(geom::geography,
                       ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_m
    FROM stops
    WHERE ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                     :radius_m)
    ORDER BY distance_m
    LIMIT :limit
    """
)


@router.get("/stops/nearby", response_model=NearbyStopsResponse)
async def nearby_stops(
    session: Annotated[AsyncSession, Depends(get_session)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    radius_m: Annotated[float, Query(gt=0, le=5000)] = 500,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NearbyStopsResponse:
    """Stops within `radius_m` metres of a point, nearest first (PostGIS, spatially indexed)."""
    rows = await session.execute(
        _NEARBY_SQL, {"lat": lat, "lon": lon, "radius_m": radius_m, "limit": limit}
    )
    return NearbyStopsResponse(
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        stops=[NearbyStop.model_validate(row, from_attributes=True) for row in rows],
    )


@router.get("/stops/{stop_id}/departures", response_model=DeparturesResponse)
async def stop_departures(stop_id: StopId, services: ServicesDep) -> DeparturesResponse:
    """Next departures from Föli SIRI Stop Monitoring, cached for 15 s per stop."""
    try:
        dataset = services.gtfs.require_dataset()
    except GtfsNotReady:
        raise gtfs_not_ready() from None
    if stop_id not in dataset.stops:
        raise not_found("STOP_NOT_FOUND", f"Stop {stop_id} does not exist in the current dataset")

    cached = services.departures.get(stop_id)
    if cached is not None:
        return cached

    try:
        raw = await services.foli.fetch_stop_monitoring(stop_id)
        status, departures = parse_stop_monitoring(raw, services.gtfs.resolve_route)
    except UpstreamClientError as exc:
        if exc.status_code != 404:
            raise upstream_unavailable() from None
        # Föli answers 404 for stops it has no monitoring data for: no departures to show.
        status, departures = "OK", []
    except (UpstreamError, SiriParseError) as exc:
        logger.warning("Stop monitoring for %s failed: %s", stop_id, exc)
        raise upstream_unavailable("Live departures are unavailable right now.") from None

    if status != "OK":
        raise upstream_unavailable("Föli is not publishing live departures right now.")
    result = DeparturesResponse(
        stop_id=stop_id, fetched_at=datetime.now(UTC), departures=departures
    )
    services.departures.put(stop_id, result)
    return result
