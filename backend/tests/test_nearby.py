import httpx
import pytest
from sqlalchemy import text

from app.services import Services
from app.stop_sync import sync_stops

pytestmark = pytest.mark.db

# Stop 1, "Turun satama (Silja)", from the fixtures.
HARBOUR = {"lat": 60.43497, "lon": 22.21966}


async def test_nearby_stops_are_ordered_by_distance(
    db_api: httpx.AsyncClient, db_services: Services
) -> None:
    assert await sync_stops(db_services.sessionmaker, db_services.gtfs.require_dataset())

    response = await db_api.get("/api/v1/stops/nearby", params={**HARBOUR, "radius_m": 3000})
    assert response.status_code == 200
    stops = response.json()["stops"]
    assert stops[0]["stop_id"] == "1"
    assert stops[0]["distance_m"] == pytest.approx(0, abs=0.5)
    distances = [s["distance_m"] for s in stops]
    assert distances == sorted(distances)
    assert all(d <= 3000 for d in distances)
    # lat/lon come back the right way round
    assert stops[0]["lat"] == pytest.approx(HARBOUR["lat"])


async def test_radius_limits_results(db_api: httpx.AsyncClient, db_services: Services) -> None:
    await sync_stops(db_services.sessionmaker, db_services.gtfs.require_dataset())
    tiny = await db_api.get("/api/v1/stops/nearby", params={**HARBOUR, "radius_m": 1})
    assert [s["stop_id"] for s in tiny.json()["stops"]] == ["1"]


async def test_sync_is_skipped_when_up_to_date_and_replaces_old_datasets(
    db_services: Services,
) -> None:
    dataset = db_services.gtfs.require_dataset()
    assert await sync_stops(db_services.sessionmaker, dataset) is True
    assert await sync_stops(db_services.sessionmaker, dataset) is False

    async with db_services.engine.begin() as conn:
        await conn.execute(text("UPDATE stops SET dataset_id = 'old' WHERE stop_id = '1'"))
        await conn.execute(
            text(
                "INSERT INTO stops VALUES ('gone', 'Removed stop', "
                "ST_SetSRID(ST_MakePoint(22, 60), 4326), 'old')"
            )
        )
    assert await sync_stops(db_services.sessionmaker, dataset) is True
    async with db_services.engine.connect() as conn:
        ids = {row[0] for row in await conn.execute(text("SELECT DISTINCT dataset_id FROM stops"))}
        gone = await conn.scalar(text("SELECT count(*) FROM stops WHERE stop_id = 'gone'"))
    assert ids == {dataset.dataset_id}
    assert gone == 0


async def test_the_spatial_index_can_serve_the_query(db_services: Services) -> None:
    await sync_stops(db_services.sessionmaker, db_services.gtfs.require_dataset())
    async with db_services.engine.connect() as conn:
        # The fixture table is tiny, so the planner would rightly prefer a sequential scan.
        # Disabling it shows whether the index CAN be used for this query shape at all.
        await conn.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in await conn.execute(
                text(
                    "EXPLAIN SELECT stop_id FROM stops WHERE ST_DWithin(geom::geography, "
                    "ST_SetSRID(ST_MakePoint(22.2, 60.4), 4326)::geography, 500)"
                )
            )
        )
    assert "stops_geog_gist" in plan
