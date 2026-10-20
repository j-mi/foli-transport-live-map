import httpx

from app.services import Services
from tests.conftest import load_fixture


async def test_lines(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/lines")
    assert response.status_code == 200
    body = response.json()
    first = body["lines"][0]
    assert first == {
        "route_id": "1",
        "short_name": "1",
        "long_name": "Lentoasema-Keskusta-Satama",
        "color": "0bbbef",
        "text_color": "000000",
    }


async def test_stops_geojson(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/stops")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/geo+json"
    body = response.json()
    assert body["type"] == "FeatureCollection"
    feature = next(f for f in body["features"] if f["properties"]["stop_id"] == "1")
    assert feature["geometry"]["coordinates"] == [22.21966, 60.43497]  # [lon, lat]


async def test_line_shape_and_unknown_line(api: httpx.AsyncClient) -> None:
    shape = await api.get("/api/v1/lines/1/shape")
    assert shape.status_code == 200
    assert len(shape.json()["features"]) == 2

    missing = await api.get("/api/v1/lines/nope/shape")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "ROUTE_NOT_FOUND",
            "message": "Line nope does not exist in the current GTFS dataset",
        }
    }


async def test_vehicles_snapshot(api: httpx.AsyncClient, services: Services) -> None:
    before = (await api.get("/api/v1/vehicles")).json()
    assert before["upstream_status"] == "PENDING"
    assert before["vehicles"] == []

    await services.poller.poll_once()
    after = (await api.get("/api/v1/vehicles")).json()
    assert after["upstream_status"] == "OK"
    assert after["seq"] == 1
    assert len(after["vehicles"]) == len(load_fixture("siri_vm.json")["result"]["vehicles"]) - 1


async def test_validation_errors_use_the_common_shape(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/lines/bad%20id!/shape")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unknown_path_uses_the_common_shape(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_health_reports_database_down(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/health")
    # The test settings point at a closed port: our own dependency is down, so 503.
    assert response.status_code == 503
    body = response.json()
    assert body["database"] == "error"
    assert body["status"] == "degraded"
    assert body["gtfs_dataset_id"] is not None


async def test_departures_are_cached_per_stop(api: httpx.AsyncClient, foli_mock) -> None:
    first = await api.get("/api/v1/stops/1/departures")
    assert first.status_code == 200
    body = first.json()
    assert body["stop_id"] == "1"
    assert len(body["departures"]) == 4
    assert body["departures"][0]["line"]

    await api.get("/api/v1/stops/1/departures")
    assert foli_mock.routes["sm_stop_1"].call_count == 1  # second request served from cache


async def test_departures_for_unknown_and_unmonitored_stops(
    api: httpx.AsyncClient, foli_mock
) -> None:
    assert (await api.get("/api/v1/stops/nope/departures")).status_code == 404

    foli_mock.get("/siri/sm/10").respond(404, text="<html>404 Not found</html>")
    empty = await api.get("/api/v1/stops/10/departures")
    assert empty.status_code == 200
    assert empty.json()["departures"] == []

    foli_mock.get("/siri/sm/100").respond(500)
    failing = await api.get("/api/v1/stops/100/departures")
    assert failing.status_code == 503
    assert failing.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"


async def test_favourites_report_database_outage(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/favourites")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


async def test_nearby_validates_coordinates(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/stops/nearby", params={"lat": 100, "lon": 22})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "query.lat"
