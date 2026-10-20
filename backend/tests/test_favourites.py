import httpx
import pytest

pytestmark = pytest.mark.db


async def test_put_is_idempotent(db_api: httpx.AsyncClient) -> None:
    first = await db_api.put("/api/v1/favourites/stops/1")
    assert first.status_code == 201
    assert first.json()["name"] == "Turun satama (Silja)"
    assert first.json()["lat"] == pytest.approx(60.43497)  # lat/lon survive the PostGIS round trip
    assert first.json()["lon"] == pytest.approx(22.21966)

    second = await db_api.put("/api/v1/favourites/stops/1")
    assert second.status_code == 200  # already there: no duplicate

    favourites = (await db_api.get("/api/v1/favourites")).json()
    assert [s["stop_id"] for s in favourites["stops"]] == ["1"]


async def test_delete_is_idempotent(db_api: httpx.AsyncClient) -> None:
    await db_api.put("/api/v1/favourites/lines/1")
    assert (await db_api.delete("/api/v1/favourites/lines/1")).status_code == 204
    assert (
        await db_api.delete("/api/v1/favourites/lines/1")
    ).status_code == 204  # absent: still 204
    assert (await db_api.get("/api/v1/favourites")).json()["lines"] == []


async def test_lines(db_api: httpx.AsyncClient) -> None:
    assert (await db_api.put("/api/v1/favourites/lines/1")).status_code == 201
    assert (await db_api.put("/api/v1/favourites/lines/1")).status_code == 200
    lines = (await db_api.get("/api/v1/favourites")).json()["lines"]
    assert [(line["route_id"], line["short_name"]) for line in lines] == [("1", "1")]


async def test_unknown_ids_are_rejected(db_api: httpx.AsyncClient) -> None:
    stop = await db_api.put("/api/v1/favourites/stops/does-not-exist")
    assert stop.status_code == 404
    assert stop.json()["error"]["code"] == "STOP_NOT_FOUND"
    line = await db_api.put("/api/v1/favourites/lines/does-not-exist")
    assert line.json()["error"]["code"] == "ROUTE_NOT_FOUND"
