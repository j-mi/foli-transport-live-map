from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from app.errors import gtfs_not_ready, not_found, upstream_unavailable
from app.integrations.foli_client import UpstreamError
from app.integrations.gtfs_cache import GtfsNotReady, UnknownRoute
from app.schemas import Line, LinesResponse
from app.services import Services, get_services

router = APIRouter(tags=["lines"])

RouteId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


@router.get("/lines", response_model=LinesResponse)
async def list_lines(services: Annotated[Services, Depends(get_services)]) -> LinesResponse:
    try:
        dataset = services.gtfs.require_dataset()
    except GtfsNotReady:
        raise gtfs_not_ready() from None
    return LinesResponse(
        dataset_id=dataset.dataset_id,
        lines=[
            Line(
                route_id=r.route_id,
                short_name=r.short_name,
                long_name=r.long_name,
                color=r.color,
                text_color=r.text_color,
            )
            for r in dataset.lines_sorted
        ],
    )


@router.get("/lines/{route_id}/shape")
async def line_shape(
    route_id: RouteId, services: Annotated[Services, Depends(get_services)]
) -> dict[str, Any]:
    """GeoJSON FeatureCollection with one LineString per direction (most common shape)."""
    try:
        return await services.gtfs.get_line_shapes(route_id)
    except GtfsNotReady:
        raise gtfs_not_ready() from None
    except UnknownRoute:
        raise not_found(
            "ROUTE_NOT_FOUND", f"Line {route_id} does not exist in the current GTFS dataset"
        ) from None
    except UpstreamError:
        raise upstream_unavailable("Could not load the route shape from Föli.") from None
