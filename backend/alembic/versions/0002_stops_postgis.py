"""GTFS stops in PostGIS for spatial queries ("stops near this point").

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE stops (
            stop_id     text PRIMARY KEY,
            name        text NOT NULL,
            geom        geometry(Point, 4326) NOT NULL,
            dataset_id  text NOT NULL
        )
        """
    )
    # Planar GiST index: serves bounding-box style queries on the geometry column (&&, ST_Within).
    op.execute("CREATE INDEX stops_geom_gist ON stops USING GIST (geom)")
    # The nearby query measures in metres, so it casts to geography: ST_DWithin(geom::geography,
    # ...). An index on `geom` cannot serve an expression on `geom::geography`, so the planner
    # would scan every row. This expression index matches the cast exactly and is what makes the
    # query use an index. (For a much larger table, a dedicated geography column with its own
    # GiST index is the cleaner design; with ~3 600 stops the expression index is enough.)
    op.execute("CREATE INDEX stops_geog_gist ON stops USING GIST ((geom::geography))")


def downgrade() -> None:
    op.execute("DROP TABLE stops")
