"""Favourite stops and lines, stored in PostgreSQL so they survive restarts.

Why PUT and not POST: adding the same favourite twice must not create a duplicate. A PUT to the
resource's own URL (`/favourites/stops/1234`) plus a primary key on `stop_id` makes the write
idempotent, so a client can safely retry after a timeout without knowing whether the first
attempt landed. 201 means "created now", 200 means "it was already there". DELETE is idempotent
the same way: 204 whether or not the row existed. (The same principle as idempotency keys on
POST, but the URL itself is the key.)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import gtfs_not_ready, not_found
from app.integrations.gtfs_cache import GtfsDataset, GtfsNotReady
from app.models import FavouriteLine, FavouriteStop
from app.schemas import FavouriteLine as FavouriteLineOut
from app.schemas import Favourites
from app.schemas import FavouriteStop as FavouriteStopOut
from app.services import Services, get_services, get_session

router = APIRouter(prefix="/favourites", tags=["favourites"])

Id = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


Session = Annotated[AsyncSession, Depends(get_session)]
ServicesDep = Annotated[Services, Depends(get_services)]

# Coordinates are stored as a PostGIS point; ST_Y is latitude and ST_X longitude.
_STOP_COLUMNS = (
    FavouriteStop.stop_id,
    FavouriteStop.name,
    func.ST_Y(FavouriteStop.geom).label("lat"),
    func.ST_X(FavouriteStop.geom).label("lon"),
    FavouriteStop.created_at,
)


def _dataset(services: Services) -> GtfsDataset:
    try:
        return services.gtfs.require_dataset()
    except GtfsNotReady:
        raise gtfs_not_ready() from None


@router.get("", response_model=Favourites)
async def list_favourites(session: Session) -> Favourites:
    stops = await session.execute(select(*_STOP_COLUMNS).order_by(FavouriteStop.created_at))
    lines = await session.execute(select(FavouriteLine).order_by(FavouriteLine.created_at))
    return Favourites(
        stops=[FavouriteStopOut.model_validate(row, from_attributes=True) for row in stops],
        lines=[
            FavouriteLineOut.model_validate(row, from_attributes=True) for row in lines.scalars()
        ],
    )


@router.put(
    "/stops/{stop_id}",
    response_model=FavouriteStopOut,
    status_code=201,
    responses={200: {"description": "Already a favourite"}, 404: {}, 503: {}},
)
async def add_favourite_stop(
    stop_id: Id, response: Response, session: Session, services: ServicesDep
) -> FavouriteStopOut:
    stop = _dataset(services).stops.get(stop_id)
    if stop is None:
        raise not_found(
            "STOP_NOT_FOUND", f"Stop {stop_id} does not exist in the current GTFS dataset"
        )

    # INSERT ... ON CONFLICT DO NOTHING RETURNING: one atomic statement, no race between a
    # "does it exist?" check and the insert. A returned row means we created it.
    statement = (
        insert(FavouriteStop)
        .values(
            stop_id=stop.stop_id,
            name=stop.name,
            geom=func.ST_SetSRID(func.ST_MakePoint(stop.lon, stop.lat), 4326),  # lon first!
        )
        .on_conflict_do_nothing(index_elements=[FavouriteStop.stop_id])
        .returning(FavouriteStop.stop_id)
    )
    created = (await session.execute(statement)).scalar_one_or_none() is not None
    await session.commit()

    row = (
        await session.execute(select(*_STOP_COLUMNS).where(FavouriteStop.stop_id == stop_id))
    ).one()
    response.status_code = 201 if created else 200
    return FavouriteStopOut.model_validate(row, from_attributes=True)


@router.delete("/stops/{stop_id}", status_code=204, response_class=Response)
async def remove_favourite_stop(stop_id: Id, session: Session) -> Response:
    await session.execute(delete(FavouriteStop).where(FavouriteStop.stop_id == stop_id))
    await session.commit()
    return Response(status_code=204)


@router.put(
    "/lines/{route_id}",
    response_model=FavouriteLineOut,
    status_code=201,
    responses={200: {"description": "Already a favourite"}, 404: {}, 503: {}},
)
async def add_favourite_line(
    route_id: Id, response: Response, session: Session, services: ServicesDep
) -> FavouriteLineOut:
    route = _dataset(services).routes.get(route_id)
    if route is None:
        raise not_found(
            "ROUTE_NOT_FOUND", f"Line {route_id} does not exist in the current GTFS dataset"
        )

    statement = (
        insert(FavouriteLine)
        .values(route_id=route.route_id, short_name=route.short_name)
        .on_conflict_do_nothing(index_elements=[FavouriteLine.route_id])
        .returning(FavouriteLine.route_id)
    )
    created = (await session.execute(statement)).scalar_one_or_none() is not None
    await session.commit()

    row = await session.get_one(FavouriteLine, route_id)
    response.status_code = 201 if created else 200
    return FavouriteLineOut.model_validate(row, from_attributes=True)


@router.delete("/lines/{route_id}", status_code=204, response_class=Response)
async def remove_favourite_line(route_id: Id, session: Session) -> Response:
    await session.execute(delete(FavouriteLine).where(FavouriteLine.route_id == route_id))
    await session.commit()
    return Response(status_code=204)
