import pytest
import respx

from app.geo import lonlat
from app.integrations.gtfs_cache import (
    UnknownRoute,
    natural_line_key,
    parse_stops,
    pick_shapes_per_direction,
)
from app.services import Services
from tests.conftest import dataset_id, load_fixture


def test_lonlat_puts_longitude_first() -> None:
    assert lonlat(60.45, 22.27) == [22.27, 60.45]


def test_most_common_shape_per_direction() -> None:
    choices = pick_shapes_per_direction(load_fixture("gtfs_trips_route_1.json"))
    assert [(c.direction_id, c.shape_id) for c in choices] == [("0", "1"), ("1", "2")]
    assert choices[0].headsign == "Satama"
    assert choices[1].headsign == "Lentoasema"


def test_shape_choice_ties_are_deterministic() -> None:
    trips = [
        {"direction_id": 0, "shape_id": "b"},
        {"direction_id": 0, "shape_id": "a"},
    ]
    assert pick_shapes_per_direction(trips)[0].shape_id == "a"


def test_stops_are_an_object_keyed_by_stop_id() -> None:
    stops = parse_stops(load_fixture("gtfs_stops.json"))
    assert stops["1"].name == "Turun satama (Silja)"
    assert stops["1"].lat == pytest.approx(60.43497)


def test_lines_sort_naturally() -> None:
    names = ["10", "2", "1A", "K1", "1", "L10", "L2", "Lautta", "100"]
    assert sorted(names, key=natural_line_key) == [
        "1",
        "1A",
        "2",
        "10",
        "100",
        "K1",
        "L2",
        "L10",
        "Lautta",
    ]


async def test_loads_one_consistent_dataset(services: Services) -> None:
    dataset = services.gtfs.require_dataset()
    assert dataset.dataset_id == dataset_id()
    assert dataset.routes["1"].short_name == "1"
    assert dataset.routes["1"].color == "0bbbef"
    assert len(dataset.stops) == len(load_fixture("gtfs_stops.json"))
    # Unchanged dataset id: nothing is reloaded.
    assert await services.gtfs.refresh() is False


async def test_resolves_vehicle_routes(services: Services) -> None:
    gtfs = services.gtfs
    assert gtfs.resolve_route("20", "10") == "20"  # __routeref is a GTFS route_id
    assert gtfs.resolve_route(None, "1") == "1"  # fall back to the line number
    assert gtfs.resolve_route("nope", "999X") is None  # unknown: no crash, just None


async def test_line_shapes_are_geojson_and_cached(
    services: Services, foli_mock: respx.MockRouter
) -> None:
    collection = await services.gtfs.get_line_shapes("1")
    assert collection["type"] == "FeatureCollection"
    assert [f["properties"]["direction_id"] for f in collection["features"]] == ["0", "1"]
    lon, lat = collection["features"][0]["geometry"]["coordinates"][0]
    assert 21 < lon < 23 and 60 < lat < 61  # [lon, lat] order

    trips_route = foli_mock.routes["trips_route_1"]
    calls = trips_route.call_count
    await services.gtfs.get_line_shapes("1")
    assert trips_route.call_count == calls  # served from the cache

    with pytest.raises(UnknownRoute):
        await services.gtfs.get_line_shapes("does-not-exist")
