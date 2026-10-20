"""Enable PostGIS and create the favourites tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The postgis/postgis image already enables the extension in POSTGRES_DB; IF NOT EXISTS keeps
    # this migration valid on a plain Postgres with PostGIS installed too.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # The primary keys are the unique constraints that make PUT /favourites/... idempotent:
    # inserting the same favourite twice cannot create a duplicate row.
    op.execute(
        """
        CREATE TABLE favourite_stops (
            stop_id     text PRIMARY KEY,
            name        text NOT NULL,
            geom        geometry(Point, 4326) NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE favourite_lines (
            route_id    text PRIMARY KEY,
            short_name  text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE favourite_lines")
    op.execute("DROP TABLE favourite_stops")
