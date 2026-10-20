"""SQLAlchemy models. The schema itself is owned by the Alembic migrations in alembic/versions.

Only user-owned state and the PostGIS copy of GTFS stops live in the database. Live vehicle
positions are ephemeral and stay in memory (see realtime/poller.py).

The app is single-user for now, so favourites have no user column. Going multi-user means a
`user_id` column, composite primary keys (user_id, stop_id) and an auth check per request.
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FavouriteStop(Base):
    __tablename__ = "favourite_stops"

    # The primary key doubles as the unique constraint that makes PUT idempotent.
    stop_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FavouriteLine(Base):
    __tablename__ = "favourite_lines"

    route_id: Mapped[str] = mapped_column(Text, primary_key=True)
    short_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StopRow(Base):
    """GTFS stops copied into PostGIS so we can run spatial queries with a spatial index."""

    __tablename__ = "stops"

    stop_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
