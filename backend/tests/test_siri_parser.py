import pytest

from app.integrations.siri_parser import (
    SiriParseError,
    parse_iso8601_duration,
    parse_stop_monitoring,
    parse_vehicle_monitoring,
)
from tests.conftest import load_fixture


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PT90S", 90),  # late
        ("-PT8S", -8),  # early
        ("PT0S", 0),
        ("PT1M30S", 90),
        ("-PT1H2M3S", -3723),
        ("P1DT2S", 86402),
        ("PT1.6S", 2),
        ("-PT13539S", -13539),  # the example in Föli's docs
    ],
)
def test_duration_parser(value: str, expected: int) -> None:
    assert parse_iso8601_duration(value) == expected


@pytest.mark.parametrize("value", ["", "P", "PT", "-PT", "90", "PTS", "abc", "PT-5S"])
def test_duration_parser_rejects_garbage(value: str) -> None:
    assert parse_iso8601_duration(value) is None


def test_parses_recorded_vehicle_monitoring() -> None:
    parsed = parse_vehicle_monitoring(load_fixture("siri_vm.json"))

    assert parsed.status == "OK"
    # The fixture has 10 vehicles; one (60666) has no position and is skipped, not crashed on.
    assert parsed.skipped == 1
    assert len(parsed.vehicles) == 9
    assert "60666" not in {v.id for v in parsed.vehicles}

    by_id = {v.id: v for v in parsed.vehicles}
    late = by_id["550022"]
    assert late.line == "10"
    assert late.delay_s == 151  # "PT151S": positive means late
    assert late.destination == "Turun satama (Silja)"
    assert late.next_stop is not None
    assert late.recorded_at.tzinfo is not None

    assert by_id["80075"].delay_s == -20  # "-PT20S": early
    assert by_id["80017"].delay_s == 0  # "PT0S" without delaysecs
    assert by_id["202095"].delay_s is None  # no delay information at all
    assert by_id["180150"].monitored is False


def test_coordinates_are_not_swapped() -> None:
    parsed = parse_vehicle_monitoring(load_fixture("siri_vm.json"))
    for vehicle in parsed.vehicles:
        # Turku region: latitude ~60 N, longitude ~22 E.
        assert 59 < vehicle.lat < 61.5
        assert 20 < vehicle.lon < 24


def test_route_resolution_uses_the_resolver() -> None:
    seen = []

    def resolver(routeref: str | None, line: str | None) -> str | None:
        seen.append((routeref, line))
        return None if line == "4" else f"route-{routeref}"

    parsed = parse_vehicle_monitoring(load_fixture("siri_vm.json"), resolver)
    by_id = {v.id: v for v in parsed.vehicles}
    assert by_id["550022"].route_id == "route-20"  # __routeref of line 10
    assert by_id["80075"].route_id is None  # unknown line: still shown, just unresolved
    assert ("20", "10") in seen


@pytest.mark.parametrize(
    ("fixture", "status"),
    [("siri_vm_pending.json", "PENDING"), ("siri_vm_no_siri_data.json", "NO_DATA")],
)
def test_special_upstream_states_are_states_not_errors(fixture: str, status: str) -> None:
    parsed = parse_vehicle_monitoring(load_fixture(fixture))
    assert parsed.status == status
    assert parsed.vehicles == []


def test_unknown_status_is_treated_as_no_data() -> None:
    parsed = parse_vehicle_monitoring({"sys": "VM", "status": "SOMETHING_NEW", "result": {}})
    assert parsed.status == "NO_DATA"


def test_minimal_vehicle_with_missing_optional_fields() -> None:
    payload = {
        "status": "OK",
        "servertime": 1791112682,
        "result": {
            "vehicles": {
                "x1": {"latitude": 60.45, "longitude": 22.27, "recordedattime": 1791112681}
            }
        },
    }
    [vehicle] = parse_vehicle_monitoring(payload).vehicles
    assert vehicle.id == "x1"  # falls back to the object key
    assert vehicle.line is None
    assert vehicle.delay_s is None
    assert vehicle.monitored is False


@pytest.mark.parametrize(
    "payload",
    [
        {"no_status": True},
        {"status": "OK", "result": {}},
        {"status": "OK", "result": {"vehicles": []}},
        "not even an object",
    ],
)
def test_malformed_documents_raise_parse_error(payload: object) -> None:
    with pytest.raises(SiriParseError):
        parse_vehicle_monitoring(payload)


def test_vehicles_with_bad_positions_are_skipped() -> None:
    payload = {
        "status": "OK",
        "result": {
            "vehicles": {
                "zero": {"latitude": 0, "longitude": 0, "recordedattime": 1},
                "text": {"latitude": "60.4", "longitude": "22.2", "recordedattime": 1},
                "range": {"latitude": 160.0, "longitude": 22.2, "recordedattime": 1},
                "no_time": {"latitude": 60.4, "longitude": 22.2},
            }
        },
    }
    parsed = parse_vehicle_monitoring(payload)
    assert parsed.vehicles == []
    assert parsed.skipped == 4


def test_parses_recorded_stop_monitoring() -> None:
    status, departures = parse_stop_monitoring(
        load_fixture("siri_sm_stop.json"), lambda routeref, line: routeref
    )
    assert status == "OK"
    assert len(departures) == 4
    assert all(d.line for d in departures)
    times = [d.expected_departure or d.aimed_departure for d in departures]
    assert times == sorted(times)
    assert departures[0].route_id is not None
